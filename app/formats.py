"""Форматы, определение типов и матрица допустимых конверсий."""

IMAGE = {
    "png", "jpg", "jpeg", "webp", "avif", "gif", "bmp", "tif", "tiff",
    "ico", "heic", "heif", "svg",
}
AUDIO = {"mp3", "wav", "ogg", "oga", "opus", "flac", "aac", "m4a", "wma", "aiff", "aif"}
VIDEO = {"mp4", "webm", "mkv", "mov", "avi", "m4v", "mpg", "mpeg", "ts", "flv", "wmv", "3gp"}
DOC = {
    "pdf", "docx", "doc", "odt", "rtf", "txt", "md", "markdown", "html", "htm",
    "xlsx", "xls", "ods", "csv", "pptx", "ppt", "odp",
}

KIND_LABEL = {
    "image": "изображение",
    "audio": "аудио",
    "video": "видео",
    "document": "документ",
}

MIME = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
    "avif": "image/avif", "gif": "image/gif", "bmp": "image/bmp", "tif": "image/tiff",
    "tiff": "image/tiff", "ico": "image/x-icon", "heic": "image/heic", "heif": "image/heif",
    "svg": "image/svg+xml",
    "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg", "oga": "audio/ogg",
    "opus": "audio/opus", "flac": "audio/flac", "aac": "audio/aac", "m4a": "audio/mp4",
    "wma": "audio/x-ms-wma", "aiff": "audio/aiff", "aif": "audio/aiff",
    "mp4": "video/mp4", "webm": "video/webm", "mkv": "video/x-matroska", "mov": "video/quicktime",
    "avi": "video/x-msvideo", "m4v": "video/x-m4v", "mpg": "video/mpeg", "mpeg": "video/mpeg",
    "ts": "video/mp2t", "flv": "video/x-flv", "wmv": "video/x-ms-wmv", "3gp": "video/3gpp",
    "pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword", "odt": "application/vnd.oasis.opendocument.text",
    "rtf": "application/rtf", "txt": "text/plain; charset=utf-8", "md": "text/markdown; charset=utf-8",
    "markdown": "text/markdown; charset=utf-8", "html": "text/html; charset=utf-8",
    "htm": "text/html; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel", "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "csv": "text/csv; charset=utf-8",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint", "odp": "application/vnd.oasis.opendocument.presentation",
}

# Что можно получить из каждого исходного расширения.
_TARGETS = {
    # изображения
    "png": ["jpg", "webp", "avif", "gif", "bmp", "tiff", "ico", "pdf"],
    "jpg": ["png", "webp", "avif", "gif", "bmp", "tiff", "ico", "pdf"],
    "jpeg": ["png", "webp", "avif", "gif", "bmp", "tiff", "ico", "pdf"],
    "webp": ["png", "jpg", "avif", "gif", "bmp", "tiff", "ico", "pdf"],
    "avif": ["png", "jpg", "webp", "gif", "bmp", "tiff", "pdf"],
    "gif": ["png", "jpg", "webp", "mp4", "webm", "avif"],
    "bmp": ["png", "jpg", "webp", "avif", "tiff", "ico", "pdf"],
    "tif": ["png", "jpg", "webp", "avif", "bmp", "pdf"],
    "tiff": ["png", "jpg", "webp", "avif", "bmp", "pdf"],
    "ico": ["png", "jpg", "webp", "ico"],
    "heic": ["png", "jpg", "webp", "avif", "pdf"],
    "heif": ["png", "jpg", "webp", "avif", "pdf"],
    "svg": ["png", "jpg", "webp", "pdf", "avif"],
    # аудио
    "mp3": ["wav", "ogg", "opus", "flac", "m4a", "aac"],
    "wav": ["mp3", "ogg", "opus", "flac", "m4a", "aac"],
    "ogg": ["mp3", "wav", "opus", "flac", "m4a", "aac"],
    "oga": ["mp3", "wav", "opus", "flac", "m4a", "aac"],
    "opus": ["mp3", "wav", "ogg", "flac", "m4a", "aac"],
    "flac": ["mp3", "wav", "ogg", "opus", "m4a", "aac"],
    "aac": ["mp3", "wav", "ogg", "opus", "flac", "m4a"],
    "m4a": ["mp3", "wav", "ogg", "opus", "flac", "aac"],
    "wma": ["mp3", "wav", "ogg", "opus", "flac", "m4a"],
    "aiff": ["mp3", "wav", "ogg", "opus", "flac", "m4a"],
    "aif": ["mp3", "wav", "ogg", "opus", "flac", "m4a"],
    # видео
    "mp4": ["webm", "mkv", "mov", "gif", "mp3", "wav"],
    "webm": ["mp4", "mkv", "mov", "gif", "mp3", "wav"],
    "mkv": ["mp4", "webm", "mov", "gif", "mp3", "wav"],
    "mov": ["mp4", "webm", "mkv", "gif", "mp3", "wav"],
    "avi": ["mp4", "webm", "mkv", "mov", "gif", "mp3", "wav"],
    "m4v": ["mp4", "webm", "mkv", "mov", "gif", "mp3", "wav"],
    "mpg": ["mp4", "webm", "mkv", "mov", "gif", "mp3", "wav"],
    "mpeg": ["mp4", "webm", "mkv", "mov", "gif", "mp3", "wav"],
    "ts": ["mp4", "webm", "mkv", "gif", "mp3", "wav"],
    "flv": ["mp4", "webm", "mkv", "gif", "mp3", "wav"],
    "wmv": ["mp4", "webm", "mkv", "gif", "mp3", "wav"],
    "3gp": ["mp4", "webm", "mkv", "gif", "mp3", "wav"],
    # документы
    "pdf": ["png", "jpg", "txt", "html"],
    "docx": ["pdf", "txt", "html", "odt", "rtf"],
    "doc": ["pdf", "txt", "html", "odt", "docx"],
    "odt": ["pdf", "txt", "html", "docx", "rtf"],
    "rtf": ["pdf", "txt", "html", "docx", "odt"],
    "txt": ["pdf", "html", "docx", "odt"],
    "md": ["pdf", "html", "txt", "docx"],
    "markdown": ["pdf", "html", "txt", "docx"],
    "html": ["pdf", "txt", "docx"],
    "htm": ["pdf", "txt", "docx"],
    "xlsx": ["pdf", "csv", "html", "ods"],
    "xls": ["pdf", "csv", "html", "ods", "xlsx"],
    "ods": ["pdf", "csv", "html", "xlsx"],
    "csv": ["pdf", "html", "xlsx", "ods"],
    "pptx": ["pdf", "html", "odp"],
    "ppt": ["pdf", "html", "odp", "pptx"],
    "odp": ["pdf", "html", "pptx"],
}


def kind_of(ext: str) -> str | None:
    ext = ext.lower().lstrip(".")
    if ext in IMAGE:
        return "image"
    if ext in AUDIO:
        return "audio"
    if ext in VIDEO:
        return "video"
    if ext in DOC:
        return "document"
    return None


def targets_for(ext: str) -> list[str]:
    return list(_TARGETS.get(ext.lower().lstrip("."), []))


def mime_of(ext: str) -> str:
    return MIME.get(ext.lower().lstrip("."), "application/octet-stream")


def is_previewable(ext: str) -> bool:
    return kind_of(ext) in ("image", "audio", "video") or ext.lower() in ("pdf", "txt", "csv", "html", "md")
