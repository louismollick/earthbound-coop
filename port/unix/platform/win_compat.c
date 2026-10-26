/* Windows named pipes for the headless harness. See win_compat.h. */
#ifdef _WIN32
#include "platform/win_compat.h"

#include <fcntl.h>
#include <io.h>
#include <string.h>
#include <windows.h>

bool win_pipe_path(const char *path) {
    return strncmp(path, "\\\\.\\pipe\\", 9) == 0;
}

/* Block until a client connects; one that connected before we waited counts */
static bool wait_client(HANDLE h) {
    return ConnectNamedPipe(h, NULL) || GetLastError() == ERROR_PIPE_CONNECTED;
}

void *win_pipe_create(const char *path, bool read) {
    HANDLE h = CreateNamedPipeA(path, read ? PIPE_ACCESS_INBOUND : PIPE_ACCESS_OUTBOUND,
                                PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT, 1, 1 << 20, 1 << 20, 0, NULL);
    return h == INVALID_HANDLE_VALUE ? NULL : h;
}

FILE *win_pipe_accept(void *pipe, bool read) {
    HANDLE h = pipe;
    if (!h)
        return NULL;
    if (!wait_client(h)) {
        CloseHandle(h);
        return NULL;
    }
    int fd = _open_osfhandle((intptr_t)h, read ? _O_RDONLY | _O_TEXT : _O_WRONLY | _O_BINARY);
    if (fd < 0) {
        CloseHandle(h);
        return NULL;
    }
    FILE *f = _fdopen(fd, read ? "r" : "wb");
    if (!f)
        _close(fd);
    return f;
}

FILE *win_pipe_open(const char *path, bool read) {
    return win_pipe_accept(win_pipe_create(path, read), read);
}

bool win_pipe_reconnect(FILE *f) {
    HANDLE h = (HANDLE)_get_osfhandle(_fileno(f));
    if (h == INVALID_HANDLE_VALUE)
        return false;
    DisconnectNamedPipe(h);
    if (!wait_client(h))
        return false;
    clearerr(f);
    return true;
}
#endif
