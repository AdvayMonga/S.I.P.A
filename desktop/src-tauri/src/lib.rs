use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;

use tauri::{AppHandle, Emitter};

fn socket_path() -> String {
    std::env::var("SIPA_SOCKET").unwrap_or_else(|_| {
        let home = std::env::var("HOME").unwrap_or_default();
        format!("{home}/.sipa/sipa.sock")
    })
}

/// Send one message to the running daemon over its Unix socket; return the reply line.
#[tauri::command]
fn ask(message: String) -> Result<String, String> {
    let path = socket_path();
    let stream = UnixStream::connect(&path).map_err(|e| format!("connect {path}: {e}"))?;
    (&stream)
        .write_all(format!("{message}\n").as_bytes())
        .map_err(|e| e.to_string())?;
    let mut line = String::new();
    BufReader::new(&stream)
        .read_line(&mut line)
        .map_err(|e| e.to_string())?;
    Ok(line.trim_end().to_string())
}

/// Hold a persistent `:subscribe` connection to the daemon and emit each proactive push (background
/// results, scheduled tasks) to the frontend as a `sipa-push` event. Reconnects if the daemon isn't
/// up yet or the link drops.
async fn subscribe_loop(app: AppHandle) {
    use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader as TokioBufReader};
    use tokio::net::UnixStream as TokioUnixStream;
    loop {
        if let Ok(mut stream) = TokioUnixStream::connect(socket_path()).await {
            if stream.write_all(b":subscribe\n").await.is_ok() {
                let mut lines = TokioBufReader::new(stream).lines();
                while let Ok(Some(line)) = lines.next_line().await {
                    let _ = app.emit("sipa-push", line);
                }
            }
        }
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![ask])
        .setup(|app| {
            tauri::async_runtime::spawn(subscribe_loop(app.handle().clone()));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
