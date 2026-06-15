use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![ask])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
