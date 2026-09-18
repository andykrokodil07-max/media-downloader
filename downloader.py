import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import re
import sys
import zipfile
import urllib.request

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    from parth_dl import InstagramDownloader
except ImportError:
    InstagramDownloader = None


# ==================== КОПИРОВАТЬ / ВСТАВИТЬ МЫШКОЙ ====================

def add_context_menu(widget, editable=True):
    menu = tk.Menu(widget, tearoff=0)

    def cut():
        try:
            widget.event_generate("<<Cut>>")
        except tk.TclError:
            pass

    def copy():
        try:
            widget.event_generate("<<Copy>>")
        except tk.TclError:
            pass

    def paste():
        try:
            widget.event_generate("<<Paste>>")
        except tk.TclError:
            pass

    def select_all(event=None):
        try:
            widget.tag_add(tk.SEL, "1.0", tk.END)
            widget.mark_set(tk.INSERT, "1.0")
            widget.see(tk.INSERT)
        except tk.TclError:
            widget.selection_range(0, tk.END)
            widget.icursor(tk.END)
        return "break"

    if editable:
        menu.add_command(label="Вырезать", command=cut)
    menu.add_command(label="Копировать", command=copy)
    if editable:
        menu.add_command(label="Вставить", command=paste)
    menu.add_separator()
    menu.add_command(label="Выделить всё", command=select_all)

    def show_menu(event):
        try:
            widget.focus_set()
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    widget.bind("<Button-3>", show_menu)
    widget.bind("<Button-2>", show_menu)
    widget.bind("<Control-a>", select_all)
    widget.bind("<Control-A>", select_all)


# ==================== АВТОСКАЧИВАНИЕ FFMPEG ====================

def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def ensure_ffmpeg(log_callback=None):
    base_dir = get_base_dir()
    ffmpeg_path = os.path.join(base_dir, "ffmpeg.exe")

    if os.path.exists(ffmpeg_path):
        return ffmpeg_path

    from shutil import which
    system_ffmpeg = which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    if log_callback:
        log_callback("Первый запуск: скачиваю ffmpeg (~40 МБ, 30-60 сек)...")

    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    zip_path = os.path.join(base_dir, "ffmpeg_temp.zip")

    try:
        urllib.request.urlretrieve(url, zip_path)
        if log_callback:
            log_callback("Распаковываю ffmpeg...")
        with zipfile.ZipFile(zip_path, "r") as z:
            for name in z.namelist():
                if name.endswith("bin/ffmpeg.exe") or name.endswith("bin\\ffmpeg.exe"):
                    with z.open(name) as src, open(ffmpeg_path, "wb") as dst:
                        dst.write(src.read())
                    break
        try:
            os.remove(zip_path)
        except OSError:
            pass
        if os.path.exists(ffmpeg_path):
            if log_callback:
                log_callback("ffmpeg готов.")
            return ffmpeg_path
        return None
    except Exception as e:
        if log_callback:
            log_callback(f"Ошибка скачивания ffmpeg: {e}")
        return None


# ==================== ЛОГИКА ЗАГРУЗКИ ====================

def is_instagram_url(url):
    return "instagram.com" in url.lower()


def is_youtube_url(url):
    return "youtube.com" in url.lower() or "youtu.be" in url.lower()


def download_instagram_parth(url, output_dir, quality, log_callback, progress_callback):
    """Скачивание Instagram через parth-dl (без cookies для публичного)."""
    if InstagramDownloader is None:
        log_callback("parth-dl не установлен.")
        return False

    log_callback("Instagram: извлекаю данные (публичный контент)...")
    progress_callback(5, "подключение...")

    try:
        dl = InstagramDownloader(verbose=False, quiet=True)
        result = dl.download(url, output_path=output_dir)
        progress_callback(100, "готово")
        log_callback(f"Instagram: готово. Сохранено в {output_dir}")
        return True

    except Exception as e:
        log_callback(f"Ошибка Instagram: {e}")
        log_callback("Совет: убедись, что пост публичный. Приватные/stories не поддерживаются.")
        return False


def download_youtube(url, output_dir, quality, log_callback, progress_callback):
    if yt_dlp is None:
        log_callback("yt-dlp не установлен.")
        return False

    quality_map = {
        "Лучшее": "bestvideo+bestaudio/best",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "Только аудио": "bestaudio/best",
    }
    fmt = quality_map.get(quality, "bestvideo+bestaudio/best")
    ffmpeg_path = ensure_ffmpeg(log_callback)

    last_reported = {"percent": -1}

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                percent = downloaded / total * 100
                if int(percent) != last_reported["percent"]:
                    last_reported["percent"] = int(percent)
                    speed = d.get("speed")
                    speed_str = f" | {speed / 1024 / 1024:.1f} МБ/с" if speed else ""
                    eta = d.get("eta")
                    eta_str = f" | осталось {eta} сек" if eta else ""
                    progress_callback(percent, f"{percent:.1f}%{speed_str}{eta_str}")
        elif d["status"] == "finished":
            log_callback("Скачивание потока завершено, идёт склейка...")
            progress_callback(99, "склейка")

    ydl_opts = {
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "format": fmt,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
    }
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    log_callback(f"YouTube: качество {quality}...")
    progress_callback(0, "подключение...")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        progress_callback(100, "готово")
        log_callback("YouTube: готово.")
        return True
    except Exception as e:
        log_callback(f"Ошибка YouTube: {e}")
        return False


# ==================== ОКНО ПРОГРАММЫ ====================

class DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Media Downloader")
        self.root.geometry("660x620")
        self.root.minsize(540, 540)

        main_frame = ttk.Frame(root, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Ссылка (YouTube / Instagram):").pack(anchor=tk.W)
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(main_frame, textvariable=self.url_var, width=70)
        self.url_entry.pack(fill=tk.X, pady=(2, 10))
        add_context_menu(self.url_entry, editable=True)

        ttk.Label(main_frame, text="Качество (для YouTube):").pack(anchor=tk.W)
        self.quality_var = tk.StringVar(value="Лучшее")
        ttk.Combobox(
            main_frame,
            textvariable=self.quality_var,
            values=["Лучшее", "1080p", "720p", "480p", "360p", "Только аудио"],
            state="readonly",
            width=20,
        ).pack(anchor=tk.W, pady=(2, 10))

        ttk.Label(main_frame, text="Папка для сохранения:").pack(anchor=tk.W)
        folder_frame = ttk.Frame(main_frame)
        folder_frame.pack(fill=tk.X, pady=(2, 10))
        self.folder_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        self.folder_entry = ttk.Entry(folder_frame, textvariable=self.folder_var, width=55)
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        add_context_menu(self.folder_entry, editable=True)

        ttk.Button(folder_frame, text="Обзор...", command=self.browse_folder).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        self.download_btn = ttk.Button(main_frame, text="Скачать", command=self.start_download)
        self.download_btn.pack(fill=tk.X, pady=(0, 10))

        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(progress_frame, text="Прогресс:").pack(side=tk.LEFT)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame, orient="horizontal", mode="determinate",
            maximum=100, variable=self.progress_var, length=400,
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self.progress_label = ttk.Label(progress_frame, text="0%", width=22, anchor=tk.E)
        self.progress_label.pack(side=tk.LEFT)

        ttk.Label(main_frame, text="Журнал (правый клик — копировать):").pack(anchor=tk.W)
        log_frame = ttk.Frame(main_frame)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD, state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        add_context_menu(self.log_text, editable=False)

        self.log("Готово. YouTube — любые видео. Instagram — публичные Reels и посты (без cookies).")

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get())
        if folder:
            self.folder_var.set(folder)

    def log(self, message):
        def _log():
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        self.root.after(0, _log)

    def update_progress(self, percent, text=""):
        def _update():
            try:
                self.progress_var.set(float(percent))
                self.progress_label.configure(text=f"{percent:.1f}%  {text}" if text else f"{percent:.1f}%")
            except (ValueError, tk.TclError):
                pass
        self.root.after(0, _update)

    def reset_progress(self):
        self.root.after(0, lambda: self.progress_var.set(0))
        self.root.after(0, lambda: self.progress_label.configure(text="0%"))

    def start_download(self):
        url = self.url_var.get().strip()
        output_dir = self.folder_var.get().strip()
        quality = self.quality_var.get()
        if not url:
            messagebox.showwarning("Ошибка", "Введите ссылку.")
            return
        if not output_dir:
            messagebox.showwarning("Ошибка", "Выберите папку.")
            return

        os.makedirs(output_dir, exist_ok=True)
        self.download_btn.configure(state=tk.DISABLED)
        self.reset_progress()

        self.log("=" * 50)
        self.log(f"URL: {url}")
        self.log(f"Папка: {output_dir}")
        if is_youtube_url(url):
            self.log(f"Качество: {quality}")
        else:
            self.log("Instagram: публичный контент, без cookies")
        self.log("")

        thread = threading.Thread(
            target=self._download_worker,
            args=(url, output_dir, quality),
            daemon=True,
        )
        thread.start()

    def _download_worker(self, url, output_dir, quality):
        success = False
        try:
            if is_youtube_url(url):
                success = download_youtube(url, output_dir, quality, self.log, self.update_progress)
            elif is_instagram_url(url):
                success = download_instagram_parth(url, output_dir, quality, self.log, self.update_progress)
            else:
                self.log("Неподдерживаемый домен.")
        except Exception as e:
            self.log(f"Ошибка: {e}")
        finally:
            self.root.after(0, lambda: self.download_btn.configure(state=tk.NORMAL))
            if success:
                self.log("Готово!")
                self.root.after(0, lambda: messagebox.showinfo("Успех", "Загрузка завершена!"))
            else:
                self.log("Не удалось. Смотри журнал выше.")
                self.update_progress(0, "ошибка")


def main():
    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
