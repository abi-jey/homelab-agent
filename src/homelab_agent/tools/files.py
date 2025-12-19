"""File operation tools for the homelab agent.


This module provides tools for file system operations with
configurable security constraints.
"""

import logging
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum file size for reading (1MB)
MAX_READ_SIZE = 1024 * 1024

# Maximum number of files to list
MAX_LIST_FILES = 500

# Paths that are restricted for safety
RESTRICTED_PATHS = frozenset({
    "/etc/shadow",
    "/etc/passwd",
    "/etc/sudoers",
    "/root/.ssh",
    "/home/*/.ssh/id_*",
})

# Extensions that are considered safe to read as text
TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".rst", ".log", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".sh", ".bash",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".xml", ".svg", ".sql", ".env", ".gitignore", ".dockerfile",
    ".service", ".timer", ".mount", ".socket",
    ".c", ".h", ".cpp", ".hpp", ".rs", ".go", ".java",
    ".rb", ".php", ".pl", ".lua", ".vim", ".zsh",
})


def _is_path_restricted(path: str) -> bool:
    """Check if a path is restricted for security.
    
    Args:
        path: The path to check.
        
    Returns:
        True if the path is restricted.
    """
    path_obj = Path(path).resolve()
    path_str = str(path_obj)
    
    for restricted in RESTRICTED_PATHS:
        if "*" in restricted:
            # Handle glob patterns
            import fnmatch
            if fnmatch.fnmatch(path_str, restricted):
                return True
        elif path_str == restricted or path_str.startswith(restricted + "/"):
            return True
    
    return False


def _is_text_file(path: Path) -> bool:
    """Check if a file is likely a text file.
    
    Args:
        path: The path to check.
        
    Returns:
        True if the file is likely text.
    """
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return True
    
    # Check MIME type
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type and mime_type.startswith("text/"):
        return True
    
    return False


async def read_file(
    path: str,
    mode: str = "line",
    start: int = 1,
    end: Optional[int] = None,
    encoding: str = "utf-8",
) -> str:
    """Read the contents of a file with optional range specification.
    
    This tool reads text files from the file system. Supports two modes
    for specifying the read range: by line numbers or by byte positions.
    
    **Mode: "line" (default)**
        - Reads lines from the file using 1-based line numbers.
        - `start`: First line to read (default: 1, the first line).
        - `end`: Last line to read (default: 100 lines from start).
        - Example: start=10, end=20 reads lines 10-20 inclusive.
    
    **Mode: "byte"**
        - Reads bytes from the file using 0-based byte offsets.
        - `start`: Starting byte position (default: 0).
        - `end`: Ending byte position exclusive (default: 4096 bytes from start).
        - Example: start=0, end=1024 reads the first 1024 bytes.
    
    Args:
        path: The absolute or relative path to the file.
            Supports ~ for home directory expansion.
        mode: Read mode - either "line" (default) or "byte".
            - "line": Read by line numbers (1-based, inclusive).
            - "byte": Read by byte positions (0-based, end exclusive).
        start: Starting position.
            - For "line" mode: First line number (1-based, default: 1).
            - For "byte" mode: Starting byte offset (0-based, default: 0).
        end: Ending position.
            - For "line" mode: Last line number inclusive (default: start + 99).
            - For "byte" mode: Ending byte offset exclusive (default: start + 4096).
            - Set to -1 to read to the end of file (up to 1MB limit).
        encoding: The file encoding (default: utf-8).
    
    Returns:
        The file contents as a formatted string with metadata,
        or an error message if the operation fails.
    
    Examples:
        Read first 50 lines (default mode):
            read_file("/var/log/syslog", end=50)
        
        Read lines 100-150:
            read_file("~/.bashrc", start=100, end=150)
        
        Read first 1KB as bytes:
            read_file("/etc/hosts", mode="byte", end=1024)
        
        Read bytes 1000-2000:
            read_file("data.txt", mode="byte", start=1000, end=2000)
        
        Read entire file (up to 1MB):
            read_file("/etc/hostname", end=-1)
    
    Notes:
        - Maximum read size is 1MB to prevent memory issues.
        - Binary files are rejected; only text files are supported.
        - Restricted system files (shadow, sudoers, SSH keys) are blocked.
    """
    logger.info(f"Reading file: {path} (mode={mode}, start={start}, end={end})")
    
    # Validate mode
    if mode not in ("line", "byte"):
        return f"❌ Invalid mode '{mode}'. Must be 'line' or 'byte'."
    
    # Expand user home
    path_obj = Path(path).expanduser().resolve()
    
    # Security check
    if _is_path_restricted(str(path_obj)):
        return f"⛔ Access denied: {path} is a restricted file."
    
    if not path_obj.exists():
        return f"❌ File not found: {path}"
    
    if not path_obj.is_file():
        return f"❌ Not a file: {path}"
    
    # Get file size
    file_size = path_obj.stat().st_size
    
    # Check if text file
    if not _is_text_file(path_obj):
        return (
            f"⚠️ {path} appears to be a binary file. "
            "Only text files can be read."
        )
    
    try:
        if mode == "byte":
            # Byte mode: 0-based, end exclusive
            if start < 0:
                start = 0
            
            # Set default end if not specified
            if end is None:
                end = start + 4096  # Default: 4KB chunk
            elif end == -1:
                end = min(file_size, MAX_READ_SIZE)
            
            # Clamp to file size and max limit
            end = min(end, file_size, start + MAX_READ_SIZE)
            
            if start >= file_size:
                return f"⚠️ Start position ({start}) is beyond file size ({file_size} bytes)."
            
            bytes_to_read = end - start
            
            with open(path_obj, "r", encoding=encoding, errors="replace") as f:
                f.seek(start)
                content = f.read(bytes_to_read)
            
            truncated = end < file_size
            trunc_msg = f" (truncated, {file_size - end} bytes remaining)" if truncated else ""
            
            return (
                f"📄 **{path_obj.name}** [bytes {start}-{end} of {file_size}]{trunc_msg}\n"
                f"```\n{content}\n```"
            )
        
        else:  # line mode
            # Line mode: 1-based, inclusive
            if start < 1:
                start = 1
            
            # Set default end if not specified, use large number for "read to end"
            read_to_end = False
            if end is None:
                end = start + 99  # Default: 100 lines
            elif end == -1:
                end = 999999999  # Read to end (effectively infinite)
                read_to_end = True
            
            if end < start:
                return f"❌ End line ({end}) must be >= start line ({start})."
            
            lines_read = []
            total_bytes = 0
            line_count = 0
            last_line_read = 0
            
            with open(path_obj, "r", encoding=encoding, errors="replace") as f:
                for i, line in enumerate(f, 1):
                    line_count = i
                    
                    if i < start:
                        continue
                    
                    if i > end:
                        break
                    
                    # Check if we'd exceed max read size
                    if total_bytes + len(line.encode(encoding, errors='replace')) > MAX_READ_SIZE:
                        lines_read.append(f"\n... (truncated at 1MB limit)")
                        break
                    
                    lines_read.append(line)
                    total_bytes += len(line.encode(encoding, errors='replace'))
                    last_line_read = i
            
            if not lines_read:
                if start > line_count:
                    return f"⚠️ Start line ({start}) is beyond file length ({line_count} lines)."
                return f"📄 **{path_obj.name}** is empty."
            
            content = "".join(lines_read)
            
            # Determine if more lines exist
            has_more = last_line_read < line_count
            more_msg = f" ({line_count - last_line_read} more lines)" if has_more else ""
            
            return (
                f"📄 **{path_obj.name}** [lines {start}-{last_line_read} of {line_count}]{more_msg}\n"
                f"```\n{content}\n```"
            )
        
    except PermissionError:
        return f"⛔ Permission denied: {path}"
    except UnicodeDecodeError:
        return f"❌ Unable to decode file with {encoding} encoding."
    except Exception as e:
        logger.exception(f"Error reading file: {e}")
        return f"❌ Error reading file: {e}"


async def write_file(
    path: str,
    content: str,
    create_directories: bool = True,
    append: bool = False,
) -> str:
    """Write text content to a file.
    
    This tool writes or appends text content to a file. It can automatically
    create parent directories if they don't exist. For safety, writing to
    system directories (/etc, /usr, /bin, etc.) is blocked.
    
    Args:
        path: The absolute or relative path to the file.
            Supports ~ for home directory expansion.
            Examples: "/tmp/test.txt", "~/notes.md", "./config.yaml"
        content: The text content to write to the file.
            Should be a string; binary content is not supported.
        create_directories: Whether to create parent directories if they
            don't exist (default: True).
            When False, fails if the parent directory doesn't exist.
        append: Whether to append to the file instead of overwriting
            (default: False).
            - False: Overwrites the file if it exists, creates if not.
            - True: Appends to the end of existing content.
    
    Returns:
        A confirmation message with the file path and bytes written,
        or an error message if the operation fails.
    
    Examples:
        Create a new file:
            write_file("/tmp/hello.txt", "Hello, World!")
        
        Append to a log file:
            write_file("~/logs/app.log", "New entry\\n", append=True)
        
        Create with nested directories:
            write_file("~/projects/new/config.yaml", "key: value")
        
        Overwrite without creating directories:
            write_file("./existing/file.txt", "new content", create_directories=False)
    
    Notes:
        - System directories are protected: /etc, /usr, /bin, /sbin, /lib, /boot
        - Restricted files (shadow, sudoers, SSH keys) cannot be written.
        - File encoding is always UTF-8.
        - Parent directories are created with default permissions (755).
    """
    logger.info(f"Writing file: {path} (append={append})")
    
    # Expand user home
    path_obj = Path(path).expanduser().resolve()
    
    # Security check
    if _is_path_restricted(str(path_obj)):
        return f"⛔ Access denied: {path} is a restricted path."
    
    # Don't allow writing to system directories
    restricted_dirs = ["/etc", "/usr", "/bin", "/sbin", "/lib", "/boot"]
    for restricted in restricted_dirs:
        if str(path_obj).startswith(restricted):
            return f"⛔ Cannot write to system directory: {restricted}"
    
    try:
        # Create directories if needed
        if create_directories:
            path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        mode = "a" if append else "w"
        with open(path_obj, mode, encoding="utf-8") as f:
            f.write(content)
        
        action = "Appended to" if append else "Written to"
        return f"✅ {action} {path_obj} ({len(content)} chars)"
        
    except PermissionError:
        return f"⛔ Permission denied: {path}"
    except FileNotFoundError:
        return f"❌ Directory does not exist: {path_obj.parent}"
    except Exception as e:
        logger.exception(f"Error writing file: {e}")
        return f"❌ Error writing file: {e}"


async def list_directory(
    path: str = ".",
    recursive: bool = False,
    show_hidden: bool = False,
    pattern: Optional[str] = None,
) -> str:
    """List the contents of a directory.
    
    This tool lists files and subdirectories in a given path, with options
    for recursive listing, hidden files, and glob pattern filtering.
    Results are sorted alphabetically and limited to 500 entries maximum.
    
    Args:
        path: The directory path to list (default: "." current directory).
            Supports ~ for home directory expansion.
            Examples: "/var/log", "~/Documents", "."
        recursive: Whether to list all contents recursively (default: False).
            - False: Lists only immediate children of the directory.
            - True: Lists all files and folders in the entire tree.
        show_hidden: Whether to include hidden files/folders (default: False).
            Hidden files are those starting with a dot (e.g., .gitignore).
        pattern: Optional glob pattern to filter results.
            Examples: "*.py" (Python files), "*.log" (log files),
            "test_*" (files starting with test_).
            When recursive=True, this searches the entire tree.
    
    Returns:
        A formatted list showing:
        - 📁 for directories (with trailing /)
        - 📄 for files (with human-readable size)
        Or an error message if the operation fails.
    
    Examples:
        List current directory:
            list_directory()
        
        List home directory with hidden files:
            list_directory("~", show_hidden=True)
        
        Find all Python files recursively:
            list_directory("/home/user/project", recursive=True, pattern="*.py")
        
        List log files in /var/log:
            list_directory("/var/log", pattern="*.log")
    
    Notes:
        - Maximum 500 entries returned to prevent overwhelming output.
        - Directories are marked with trailing / for clarity.
        - File sizes shown as B, KB, MB, or GB as appropriate.
        - Permission errors on individual items are silently skipped.
    """
    logger.info(f"Listing directory: {path}")
    
    # Expand user home
    path_obj = Path(path).expanduser().resolve()
    
    if not path_obj.exists():
        return f"❌ Directory not found: {path}"
    
    if not path_obj.is_dir():
        return f"❌ Not a directory: {path}"
    
    try:
        entries = []
        count = 0
        
        if recursive:
            if pattern:
                items = path_obj.rglob(pattern)
            else:
                items = path_obj.rglob("*")
        else:
            if pattern:
                items = path_obj.glob(pattern)
            else:
                items = path_obj.iterdir()
        
        for item in sorted(items):
            # Skip hidden files unless requested
            if not show_hidden and item.name.startswith("."):
                continue
            
            count += 1
            if count > MAX_LIST_FILES:
                entries.append(f"\n... (truncated, max {MAX_LIST_FILES} entries)")
                break
            
            # Format entry
            rel_path = item.relative_to(path_obj) if recursive else item.name
            if item.is_dir():
                entries.append(f"📁 {rel_path}/")
            else:
                size = item.stat().st_size
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size // 1024}KB"
                else:
                    size_str = f"{size // (1024 * 1024)}MB"
                entries.append(f"📄 {rel_path} ({size_str})")
        
        if not entries:
            return f"📂 {path_obj} is empty"
        
        header = f"📂 **{path_obj}** ({len(entries)} items)\n"
        return header + "\n".join(entries)
        
    except PermissionError:
        return f"⛔ Permission denied: {path}"
    except Exception as e:
        logger.exception(f"Error listing directory: {e}")
        return f"❌ Error listing directory: {e}"


async def delete_file(
    path: str,
    force: bool = False,
) -> str:
    """Delete a file or directory.
    
    This tool deletes files and directories from the file system. For safety,
    non-empty directories require explicit force=True. System directories
    are protected and cannot be deleted.
    
    Args:
        path: The path to the file or directory to delete.
            Supports ~ for home directory expansion.
            Examples: "/tmp/old_file.txt", "~/Downloads/temp/"
        force: Whether to delete non-empty directories recursively
            (default: False).
            - False: Only deletes files and empty directories.
            - True: Recursively deletes directories and all contents.
            ⚠️ Use with extreme caution - this is irreversible!
    
    Returns:
        A confirmation message with the deleted path,
        or an error message if the operation fails.
    
    Examples:
        Delete a single file:
            delete_file("/tmp/old_file.txt")
        
        Delete an empty directory:
            delete_file("~/empty_folder/")
        
        Delete a directory with contents (dangerous!):
            delete_file("~/Downloads/temp/", force=True)
    
    Notes:
        - Protected directories: /etc, /usr, /bin, /sbin, /lib, /boot, /var, /root
        - Exceptions: /var/tmp and /var/log subdirectories can be deleted.
        - Restricted files (shadow, sudoers, SSH keys) cannot be deleted.
        - Symlinks are removed (not their targets).
        - No trash/recycle bin - deletion is permanent.
    """
    logger.info(f"Deleting: {path} (force={force})")
    
    # Expand user home
    path_obj = Path(path).expanduser().resolve()
    
    # Security check
    if _is_path_restricted(str(path_obj)):
        return f"⛔ Access denied: {path} is a restricted path."
    
    # Don't allow deleting system directories
    restricted_dirs = ["/etc", "/usr", "/bin", "/sbin", "/lib", "/boot", "/var", "/root"]
    for restricted in restricted_dirs:
        if str(path_obj) == restricted or str(path_obj).startswith(restricted + "/"):
            if not str(path_obj).startswith("/var/tmp") and not str(path_obj).startswith("/var/log"):
                return f"⛔ Cannot delete from system directory: {restricted}"
    
    if not path_obj.exists():
        return f"❌ Path not found: {path}"
    
    try:
        if path_obj.is_file():
            path_obj.unlink()
            return f"🗑️ Deleted file: {path_obj}"
        
        elif path_obj.is_dir():
            if force:
                import shutil
                shutil.rmtree(path_obj)
                return f"🗑️ Deleted directory (recursively): {path_obj}"
            else:
                try:
                    path_obj.rmdir()
                    return f"🗑️ Deleted empty directory: {path_obj}"
                except OSError:
                    return (
                        f"⚠️ Directory is not empty: {path_obj}\n"
                        "Use force=True to delete non-empty directories."
                    )
        
        else:
            return f"❌ Unknown file type: {path}"
        
    except PermissionError:
        return f"⛔ Permission denied: {path}"
    except Exception as e:
        logger.exception(f"Error deleting: {e}")
        return f"❌ Error deleting: {e}"


async def file_info(path: str) -> str:
    """Get detailed metadata about a file or directory.
    
    This tool provides comprehensive information about a file or directory,
    including size, permissions, ownership, timestamps, and type details.
    
    Args:
        path: The path to the file or directory to inspect.
            Supports ~ for home directory expansion.
            Examples: "/etc/hostname", "~/Documents", "/var/log/syslog"
    
    Returns:
        Formatted file information including:
        - **Path**: Absolute resolved path
        - **Type**: File (with MIME type), Directory (with item count), or Symlink (with target)
        - **Size**: Human-readable size (bytes, KB, MB, GB)
        - **Permissions**: Unix permission string (e.g., -rw-r--r--)
        - **Owner**: User and group ownership
        - **Modified**: Last modification timestamp (ISO format)
        - **Created**: Creation/change timestamp (ISO format)
        
        Or an error message if the operation fails.
    
    Examples:
        Check a configuration file:
            file_info("/etc/nginx/nginx.conf")
        
        Inspect home directory:
            file_info("~")
        
        Check a log file size and permissions:
            file_info("/var/log/syslog")
    
    Notes:
        - MIME type detection based on file extension.
        - Directory item count may fail silently on permission errors.
        - Symlink targets are shown but not followed for other metadata.
        - Timestamps are in local timezone, ISO 8601 format.
    """
    logger.info(f"Getting info for: {path}")
    
    # Expand user home
    path_obj = Path(path).expanduser().resolve()
    
    if not path_obj.exists():
        return f"❌ Path not found: {path}"
    
    try:
        stat = path_obj.stat()
        
        # Format size
        size = stat.st_size
        if size < 1024:
            size_str = f"{size} bytes"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{size / (1024 * 1024 * 1024):.1f} GB"
        
        # Format permissions
        import stat as stat_module
        mode = stat.st_mode
        perms = stat_module.filemode(mode)
        
        # Format times
        from datetime import datetime
        mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
        ctime = datetime.fromtimestamp(stat.st_ctime).isoformat()
        
        # Get type
        if path_obj.is_file():
            file_type = "File"
            mime_type, _ = mimetypes.guess_type(str(path_obj))
            if mime_type:
                file_type += f" ({mime_type})"
        elif path_obj.is_dir():
            file_type = "Directory"
            # Count contents
            try:
                items = list(path_obj.iterdir())
                file_type += f" ({len(items)} items)"
            except PermissionError:
                pass
        elif path_obj.is_symlink():
            file_type = f"Symlink → {path_obj.readlink()}"
        else:
            file_type = "Unknown"
        
        # Get owner
        try:
            import pwd
            import grp
            owner = pwd.getpwuid(stat.st_uid).pw_name
            group = grp.getgrgid(stat.st_gid).gr_name
        except (KeyError, ImportError):
            owner = str(stat.st_uid)
            group = str(stat.st_gid)
        
        info = f"""📋 **File Information**
**Path:** {path_obj}
**Type:** {file_type}
**Size:** {size_str}
**Permissions:** {perms}
**Owner:** {owner}:{group}
**Modified:** {mtime}
**Created:** {ctime}"""
        
        return info
        
    except PermissionError:
        return f"⛔ Permission denied: {path}"
    except Exception as e:
        logger.exception(f"Error getting file info: {e}")
        return f"❌ Error getting file info: {e}"


async def apply_patch(
    patch: str,
    base_path: str = ".",
    strip: int = 1,
    dry_run: bool = False,
) -> str:
    """Apply a unified diff (git patch) to files.
    
    This tool applies a unified diff patch to one or more files. The patch
    format should be standard unified diff as produced by `git diff` or
    `diff -u`. Supports creating new files and modifying existing ones.
    
    **Patch Format:**
    The patch should be in unified diff format with file headers:
    ```
    --- a/path/to/file.txt
    +++ b/path/to/file.txt
    @@ -start,count +start,count @@
     context line
    -removed line
    +added line
     context line
    ```
    
    Args:
        patch: The unified diff patch content as a string.
            Should include file headers (--- and +++) and hunks.
            Can contain patches for multiple files.
        base_path: Base directory path for applying the patch
            (default: "." current directory).
            File paths in the patch are relative to this directory.
            Supports ~ for home directory expansion.
        strip: Number of leading path components to strip from file names
            (default: 1, like `patch -p1`).
            - strip=0: Use paths as-is from the patch
            - strip=1: Remove first component (e.g., a/file.txt → file.txt)
            - strip=2: Remove first two components
        dry_run: If True, validate the patch without applying it
            (default: False).
            Useful for checking if a patch will apply cleanly.
    
    Returns:
        A summary of applied changes including:
        - Files modified, created, or that would be changed (dry run)
        - Number of hunks applied per file
        - Any errors or conflicts encountered
        
        Or an error message if the patch fails.
    
    Examples:
        Apply a simple patch:
            apply_patch('''
            --- a/README.md
            +++ b/README.md
            @@ -1,3 +1,4 @@
             # Project
            +New description line
             
             More content
            ''')
        
        Apply patch to a specific directory:
            apply_patch(patch_content, base_path="/home/user/project")
        
        Validate without applying:
            apply_patch(patch_content, dry_run=True)
        
        Apply patch without stripping (paths as-is):
            apply_patch(patch_content, strip=0)
    
    Notes:
        - Uses Python's difflib for parsing; complex patches may need git.
        - Context lines must match exactly for hunks to apply.
        - New files are created if the patch indicates file creation.
        - Deleted files (empty +++ target) are removed.
        - System directories are protected from modification.
        - Backup files are NOT created - use version control.
        - Fuzzy matching is not supported; patches must apply exactly.
    """
    import re
    import subprocess
    import tempfile
    
    logger.info(f"Applying patch (base={base_path}, strip={strip}, dry_run={dry_run})")
    
    # Expand base path
    base_path_obj = Path(base_path).expanduser().resolve()
    
    if not base_path_obj.exists():
        return f"❌ Base path not found: {base_path}"
    
    if not base_path_obj.is_dir():
        return f"❌ Base path is not a directory: {base_path}"
    
    # Try to use git apply first (more robust)
    try:
        # Write patch to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
            f.write(patch)
            patch_file = f.name
        
        try:
            # Check if we're in a git repo
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=str(base_path_obj),
                capture_output=True,
                text=True,
            )
            is_git_repo = result.returncode == 0
            
            if is_git_repo:
                # Use git apply
                cmd = ["git", "apply", f"-p{strip}"]
                if dry_run:
                    cmd.append("--check")
                cmd.append(patch_file)
                
                result = subprocess.run(
                    cmd,
                    cwd=str(base_path_obj),
                    capture_output=True,
                    text=True,
                )
                
                if result.returncode == 0:
                    # Parse the patch to report what was done
                    files_modified = _parse_patch_files(patch, strip)
                    action = "Would modify" if dry_run else "Modified"
                    
                    if not files_modified:
                        return "⚠️ Patch appears empty or could not parse file names."
                    
                    file_list = "\n".join(f"  📄 {f}" for f in files_modified)
                    return f"✅ Patch applied successfully!\n\n{action} files:\n{file_list}"
                else:
                    error = result.stderr.strip() or result.stdout.strip()
                    return f"❌ Patch failed to apply:\n```\n{error}\n```"
            else:
                # Fall back to patch command
                return await _apply_patch_native(patch, base_path_obj, strip, dry_run)
                
        finally:
            # Clean up temp file
            Path(patch_file).unlink(missing_ok=True)
            
    except FileNotFoundError:
        # git not available, use native
        return await _apply_patch_native(patch, base_path_obj, strip, dry_run)
    except Exception as e:
        logger.exception(f"Error applying patch: {e}")
        return f"❌ Error applying patch: {e}"


def _parse_patch_files(patch: str, strip: int) -> list[str]:
    """Parse file names from a unified diff patch.
    
    Args:
        patch: The patch content.
        strip: Number of path components to strip.
        
    Returns:
        List of file paths that would be modified.
    """
    import re
    
    files = []
    # Match +++ lines (the target file in unified diff)
    for match in re.finditer(r'^\+\+\+ ([^\t\n]+)', patch, re.MULTILINE):
        path = match.group(1).strip()
        
        # Skip /dev/null (indicates file deletion)
        if path == "/dev/null":
            continue
        
        # Strip leading components
        if strip > 0:
            parts = path.split('/')
            if len(parts) > strip:
                path = '/'.join(parts[strip:])
            else:
                path = parts[-1] if parts else path
        
        if path and path not in files:
            files.append(path)
    
    return files


async def _apply_patch_native(
    patch: str,
    base_path: Path,
    strip: int,
    dry_run: bool,
) -> str:
    """Apply patch using native Python implementation.
    
    This is a fallback when git is not available.
    
    Args:
        patch: The unified diff patch content.
        base_path: Base directory for applying.
        strip: Path components to strip.
        dry_run: Whether to only validate.
        
    Returns:
        Result message.
    """
    import re
    
    # Parse patch into file sections
    file_pattern = re.compile(
        r'^--- ([^\t\n]+).*\n\+\+\+ ([^\t\n]+).*\n((?:@@.*\n(?:[ +\-].*\n|.*\n)*)+)',
        re.MULTILINE
    )
    
    results = []
    errors = []
    
    for match in file_pattern.finditer(patch):
        old_file = match.group(1).strip()
        new_file = match.group(2).strip()
        hunks_text = match.group(3)
        
        # Strip path components from new file
        if strip > 0 and new_file != "/dev/null":
            parts = new_file.split('/')
            if len(parts) > strip:
                new_file = '/'.join(parts[strip:])
            else:
                new_file = parts[-1] if parts else new_file
        
        # Determine target file
        if new_file == "/dev/null":
            # File deletion
            if strip > 0:
                parts = old_file.split('/')
                if len(parts) > strip:
                    target_file = '/'.join(parts[strip:])
                else:
                    target_file = parts[-1] if parts else old_file
            else:
                target_file = old_file
            
            target_path = base_path / target_file
            
            if _is_path_restricted(str(target_path)):
                errors.append(f"⛔ Cannot delete restricted file: {target_file}")
                continue
            
            if dry_run:
                results.append(f"🗑️ Would delete: {target_file}")
            else:
                if target_path.exists():
                    target_path.unlink()
                    results.append(f"🗑️ Deleted: {target_file}")
                else:
                    errors.append(f"⚠️ File not found for deletion: {target_file}")
            continue
        
        target_path = base_path / new_file
        
        # Security check
        if _is_path_restricted(str(target_path)):
            errors.append(f"⛔ Cannot modify restricted file: {new_file}")
            continue
        
        # Check system directories
        restricted_dirs = ["/etc", "/usr", "/bin", "/sbin", "/lib", "/boot"]
        is_restricted = any(
            str(target_path.resolve()).startswith(d) 
            for d in restricted_dirs
        )
        if is_restricted:
            errors.append(f"⛔ Cannot modify system file: {new_file}")
            continue
        
        # Apply hunks
        if old_file == "/dev/null":
            # New file creation
            if dry_run:
                results.append(f"📝 Would create: {new_file}")
            else:
                # Extract content from hunks (all + lines)
                content_lines = []
                for line in hunks_text.split('\n'):
                    if line.startswith('+') and not line.startswith('+++'):
                        content_lines.append(line[1:])
                
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text('\n'.join(content_lines))
                results.append(f"📝 Created: {new_file}")
        else:
            # Modify existing file
            if not target_path.exists():
                errors.append(f"❌ File not found: {new_file}")
                continue
            
            try:
                original = target_path.read_text()
                patched = _apply_hunks(original, hunks_text)
                
                if patched is None:
                    errors.append(f"⚠️ Patch does not apply cleanly: {new_file}")
                    continue
                
                if dry_run:
                    results.append(f"✏️ Would modify: {new_file}")
                else:
                    target_path.write_text(patched)
                    results.append(f"✏️ Modified: {new_file}")
                    
            except Exception as e:
                errors.append(f"❌ Error patching {new_file}: {e}")
    
    # Build result message
    output_parts = []
    
    if results:
        action = "Dry run results" if dry_run else "Changes applied"
        output_parts.append(f"✅ {action}:\n" + "\n".join(f"  {r}" for r in results))
    
    if errors:
        output_parts.append("⚠️ Errors:\n" + "\n".join(f"  {e}" for e in errors))
    
    if not results and not errors:
        return "⚠️ No changes detected in patch."
    
    return "\n\n".join(output_parts)


def _apply_hunks(original: str, hunks_text: str) -> Optional[str]:
    """Apply patch hunks to original content.
    
    Args:
        original: Original file content.
        hunks_text: The hunk sections from the patch.
        
    Returns:
        Patched content, or None if hunks don't apply.
    """
    import re
    
    lines = original.split('\n')
    result_lines = lines.copy()
    offset = 0
    
    # Parse hunks
    hunk_pattern = re.compile(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
    
    hunks = []
    current_hunk = None
    
    for line in hunks_text.split('\n'):
        match = hunk_pattern.match(line)
        if match:
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = {
                'old_start': int(match.group(1)),
                'old_count': int(match.group(2)) if match.group(2) else 1,
                'new_start': int(match.group(3)),
                'new_count': int(match.group(4)) if match.group(4) else 1,
                'lines': [],
            }
        elif current_hunk is not None:
            if line.startswith(' ') or line.startswith('-') or line.startswith('+'):
                current_hunk['lines'].append(line)
            elif line.startswith('\\'):
                # "No newline at end of file" marker
                pass
    
    if current_hunk:
        hunks.append(current_hunk)
    
    # Apply each hunk
    for hunk in hunks:
        old_start = hunk['old_start'] - 1 + offset  # Convert to 0-based
        
        # Build expected old lines and new lines
        old_lines = []
        new_lines = []
        
        for line in hunk['lines']:
            if line.startswith(' '):
                old_lines.append(line[1:])
                new_lines.append(line[1:])
            elif line.startswith('-'):
                old_lines.append(line[1:])
            elif line.startswith('+'):
                new_lines.append(line[1:])
        
        # Verify context matches
        if old_start + len(old_lines) > len(result_lines):
            return None  # Hunk doesn't fit
        
        for i, expected in enumerate(old_lines):
            if old_start + i >= len(result_lines):
                return None
            if result_lines[old_start + i] != expected:
                return None  # Context mismatch
        
        # Apply the hunk
        result_lines = (
            result_lines[:old_start] + 
            new_lines + 
            result_lines[old_start + len(old_lines):]
        )
        
        # Update offset for subsequent hunks
        offset += len(new_lines) - len(old_lines)
    
    return '\n'.join(result_lines)
