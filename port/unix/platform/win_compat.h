/*
 * Windows (MinGW-w64) shims for the desktop port. Everything here is a no-op
 * include on other platforms.
 *
 * - mkdir(path, mode): MSVCRT's mkdir takes no mode.
 * - Named pipes stand in for the FIFOs the headless harness uses on Unix
 *   (`--session` commands, `--record-video` frames). A path that starts with
 *   \\.\pipe\ makes the game the pipe's server: win_pipe_open() creates the
 *   pipe and blocks until the harness connects (as opening a FIFO blocks until
 *   the other end opens it), then wraps it in a FILE *. For a session, every
 *   driver command is a new client (pt.py `do`), so on EOF the session calls
 *   win_pipe_reconnect() and waits for the next one, which is what a FIFO the
 *   game holds open read-write does on Unix.
 */
#ifndef PLATFORM_WIN_COMPAT_H
#define PLATFORM_WIN_COMPAT_H

#ifdef _WIN32
#include <direct.h>
#include <stdbool.h>
#include <stdio.h>

#define mkdir(path, mode) _mkdir(path)

/* true for a \\.\pipe\NAME path */
bool win_pipe_path(const char *path);
/* Create the pipe (NULL on failure); then win_pipe_accept() waits for a
 * client and returns the pipe as a FILE * (NULL on failure). read: inbound
 * ("r", text mode); else outbound ("wb"). */
void *win_pipe_create(const char *path, bool read);
FILE *win_pipe_accept(void *pipe, bool read);
/* Both at once */
FILE *win_pipe_open(const char *path, bool read);
/* Drop the current client of an inbound pipe from win_pipe_open() and wait
 * for the next. false when the pipe is unusable. */
bool win_pipe_reconnect(FILE *f);
#endif

#endif
