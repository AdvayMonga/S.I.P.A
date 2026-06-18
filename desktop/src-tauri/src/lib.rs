use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use tauri::{AppHandle, Emitter, State};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;
use tokio::sync::oneshot;

const ASK_PREFIX: &str = "\u{1}?"; // a daemon line starting with this is a question, not a reply
const TELEMETRY_PREFIX: &str = "\u{1}T"; // a pushed line starting with this is a telemetry snapshot (JSON)

fn socket_path() -> String {
    std::env::var("SIPA_SOCKET").unwrap_or_else(|_| {
        let home = std::env::var("HOME").unwrap_or_default();
        format!("{home}/.sipa/sipa.sock")
    })
}

/// Pending approval questions, keyed by id, awaiting the user's answer from the frontend.
#[derive(Default)]
struct Approvals {
    pending: Mutex<HashMap<String, oneshot::Sender<String>>>,
    counter: AtomicU64,
}

/// Send one message to a specific thread. Mid-turn, the daemon may ask a question (ASK_PREFIX line);
/// we surface it to the UI, wait for the user's answer, write it back, and read until the reply.
#[tauri::command]
async fn ask(
    app: AppHandle,
    state: State<'_, Approvals>,
    thread_id: String,
    message: String,
) -> Result<String, String> {
    let path = socket_path();
    let stream = UnixStream::connect(&path)
        .await
        .map_err(|e| format!("connect {path}: {e}"))?;
    let (read_half, mut write_half) = stream.into_split();
    write_half
        .write_all(format!(":thread {thread_id}\n{message}\n").as_bytes())
        .await
        .map_err(|e| e.to_string())?;
    let mut lines = BufReader::new(read_half).lines();
    loop {
        match lines.next_line().await.map_err(|e| e.to_string())? {
            None => return Err("daemon closed the connection".into()),
            Some(line) => match line.strip_prefix(ASK_PREFIX) {
                Some(question) => {
                    let answer = request_approval(&app, &state, question);
                    write_half
                        .write_all(format!("{}\n", answer.await).as_bytes())
                        .await
                        .map_err(|e| e.to_string())?;
                }
                None => return Ok(line),
            },
        }
    }
}

/// Create a new thread; the daemon's first reply line is its id.
#[tauri::command]
async fn new_thread() -> Result<String, String> {
    let (read_half, mut write_half) = connect().await?.into_split();
    write_half
        .write_all(b":thread new\n")
        .await
        .map_err(|e| e.to_string())?;
    BufReader::new(read_half)
        .lines()
        .next_line()
        .await
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "daemon closed the connection".into())
}

/// Fire a one-shot control verb (`stop` / `resolve`) at a thread and await its ack.
async fn control(verb: &str, id: &str) -> Result<(), String> {
    let (read_half, mut write_half) = connect().await?.into_split();
    write_half
        .write_all(format!(":{verb} {id}\n").as_bytes())
        .await
        .map_err(|e| e.to_string())?;
    let _ = BufReader::new(read_half).lines().next_line().await; // ack ("ok")
    Ok(())
}

#[tauri::command]
async fn stop_thread(id: String) -> Result<(), String> {
    control("stop", &id).await
}

#[tauri::command]
async fn resolve_thread(id: String) -> Result<(), String> {
    control("resolve", &id).await
}

async fn connect() -> Result<UnixStream, String> {
    let path = socket_path();
    UnixStream::connect(&path)
        .await
        .map_err(|e| format!("connect {path}: {e}"))
}

/// Emit the question to the frontend and await the answer the `approve` command will deliver.
async fn request_approval(app: &AppHandle, state: &Approvals, question: &str) -> String {
    let id = state.counter.fetch_add(1, Ordering::Relaxed).to_string();
    let (tx, rx) = oneshot::channel();
    state.pending.lock().unwrap().insert(id.clone(), tx);
    let _ = app.emit("approval-request", serde_json::json!({"id": id, "question": question}));
    rx.await.unwrap_or_else(|_| "n".into()) // frontend gone → treat as deny
}

/// The frontend's answer to an approval question.
#[tauri::command]
fn approve(state: State<'_, Approvals>, id: String, answer: String) -> Result<(), String> {
    if let Some(tx) = state.pending.lock().unwrap().remove(&id) {
        let _ = tx.send(answer);
    }
    Ok(())
}

/// Persistent `:subscribe` connection — route each pushed line by its typed prefix: telemetry
/// snapshots (`{topic, …}`) → `sipa-telemetry`; everything else (background results, scheduled
/// tasks) → `sipa-push`. Reconnects if the daemon is down / the link drops.
async fn subscribe_loop(app: AppHandle) {
    loop {
        if let Ok(mut stream) = UnixStream::connect(socket_path()).await {
            if stream.write_all(b":subscribe\n").await.is_ok() {
                let mut lines = BufReader::new(stream).lines();
                while let Ok(Some(line)) = lines.next_line().await {
                    match line.strip_prefix(TELEMETRY_PREFIX) {
                        Some(json) => {
                            if let Ok(value) = serde_json::from_str::<serde_json::Value>(json) {
                                let _ = app.emit("sipa-telemetry", value);
                            }
                        }
                        None => {
                            let _ = app.emit("sipa-push", line);
                        }
                    }
                }
            }
        }
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Approvals::default())
        .invoke_handler(tauri::generate_handler![
            ask,
            approve,
            new_thread,
            stop_thread,
            resolve_thread
        ])
        .setup(|app| {
            tauri::async_runtime::spawn(subscribe_loop(app.handle().clone()));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
