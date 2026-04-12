import os
import time
from threading import Timer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.indexer.builder.builder import run_single_file_pipeline
from src.indexer.scanner.scanner import SUPPORTED_EXTENSIONS

class DebouncedPipelineHandler(FileSystemEventHandler):
    """
    Step 7 Watcher Logic:
    Monitors repo for changes. Ignores specified directories implicitly because 
    the pipeline only acts on SUPPORTED_EXTENSIONS. Debounces rapid format-on-save changes.
    """
    def __init__(self, debounce_time=0.3):
        self.debounce_time = debounce_time
        self._timers = {}

    def _process_file(self, filepath):
        # ensure extension is valid before wasting cycles
        ext = os.path.splitext(filepath)[1]
        
        # Guard clause: make sure it's a code file and it's not hidden in .git or node_modules
        if ext in SUPPORTED_EXTENSIONS and ".git" not in filepath and "node_modules" not in filepath:
            print(f"\n[Watcher] Event triggered for: {filepath}")
            run_single_file_pipeline(filepath)
            
        if filepath in self._timers:
            del self._timers[filepath]

    def _debounce(self, filepath):
        # Cancel running timers for this file to debounce "format on save" 
        # which triggers multiple swift modify events
        if filepath in self._timers:
            self._timers[filepath].cancel()
        
        timer = Timer(self.debounce_time, self._process_file, args=[filepath])
        self._timers[filepath] = timer
        timer.start()

    def on_created(self, event):
        if not event.is_directory:
            self._debounce(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._debounce(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._debounce(event.src_path)
            
def start_watcher(repo_path: str):
    """Kicks off watchdog daemon locking onto the main thread."""
    print(f"[*] Starting robust watchdog observer on '{repo_path}' (300ms debounce)")
    event_handler = DebouncedPipelineHandler(debounce_time=0.3)
    observer = Observer()
    observer.schedule(event_handler, repo_path, recursive=True)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Stopping watcher...")
        observer.stop()
        
    observer.join()
