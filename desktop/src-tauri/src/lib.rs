use tauri::{AppHandle, Emitter};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;

const TELEMETRY_PREFIX: &str = "\u{1}T"; // a pushed line with this prefix is a structured JSON event

fn socket_path() -> String {
    std::env::var("SIPA_SOCKET").unwrap_or_else(|_| {
        let home = std::env::var("HOME").unwrap_or_default();
        format!("{home}/.sipa/sipa.sock")
    })
}

async fn connect() -> Result<UnixStream, String> {
    let path = socket_path();
    UnixStream::connect(&path)
        .await
        .map_err(|e| format!("connect {path}: {e}"))
}

/// Send a message to a thread, fire-and-forget: the daemon acks "queued" and the reply arrives later
/// as a pushed `reply` event over the subscribe channel (routed by thread on the frontend).
#[tauri::command]
async fn send(thread_id: String, message: String) -> Result<(), String> {
    let (read_half, mut write_half) = connect().await?.into_split();
    write_half
        .write_all(format!(":thread {thread_id}\n{message}\n").as_bytes())
        .await
        .map_err(|e| e.to_string())?;
    let _ = BufReader::new(read_half).lines().next_line().await; // ack ("queued")
    Ok(())
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

/// Answer a mid-turn approval (the daemon pushed an `approval` event with this id).
#[tauri::command]
async fn answer_approval(id: String, answer: String) -> Result<(), String> {
    control(&format!(":answer {id} {answer}")).await
}

#[tauri::command]
async fn stop_thread(id: String) -> Result<(), String> {
    control(&format!(":stop {id}")).await
}

#[tauri::command]
async fn resolve_thread(id: String) -> Result<(), String> {
    control(&format!(":resolve {id}")).await
}

/// Fire a one-shot control line at the daemon and await its ack.
async fn control(line: &str) -> Result<(), String> {
    let (read_half, mut write_half) = connect().await?.into_split();
    write_half
        .write_all(format!("{line}\n").as_bytes())
        .await
        .map_err(|e| e.to_string())?;
    let _ = BufReader::new(read_half).lines().next_line().await; // ack
    Ok(())
}

/// Persistent `:subscribe` connection — structured events (`{topic, …}`: replies, approvals, cost,
/// threads) emit as `sipa-telemetry`; plain proactive lines emit as `sipa-push`. The frontend routes
/// by topic. Reconnects if the daemon is down / the link drops.
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
        .invoke_handler(tauri::generate_handler![
            send,
            new_thread,
            stop_thread,
            resolve_thread,
            answer_approval
        ])
        .setup(|app| {
            tauri::async_runtime::spawn(subscribe_loop(app.handle().clone()));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
