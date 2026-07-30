use crate::services::{
    fs_create_directory, fs_create_file, fs_delete_path, fs_rename_path,
    read_directory_tree as do_read_tree, read_file_content, write_file_content, FileNode,
};

#[tauri::command]
pub fn read_directory_tree(path: String) -> Result<FileNode, String> {
    println!("[Rust] read_directory_tree called for: {}", path);
    do_read_tree(&path)
}

#[tauri::command]
pub fn read_file(path: String) -> Result<String, String> {
    println!("[Rust] read_file called for: {}", path);
    read_file_content(&path)
}

#[tauri::command]
pub fn write_file(path: String, content: String) -> Result<(), String> {
    write_file_content(&path, &content)
}

#[tauri::command]
pub fn create_file(path: String) -> Result<(), String> {
    fs_create_file(&path)
}

#[tauri::command]
pub fn create_directory(path: String) -> Result<(), String> {
    fs_create_directory(&path)
}

#[tauri::command]
pub fn delete_path(path: String) -> Result<(), String> {
    fs_delete_path(&path)
}

#[tauri::command]
pub fn rename_path(old_path: String, new_path: String) -> Result<(), String> {
    fs_rename_path(&old_path, &new_path)
}
