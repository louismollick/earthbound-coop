#ifndef EB_NET_LAUNCHER_H
#define EB_NET_LAUNCHER_H

/*
 * The launcher: a black screen before the game with Play, Host online and Join
 * online. Host asks for the relay (remembered), Join for an invite (filled from
 * the clipboard, or the last one), and both start the Session (net_start) right
 * there, so a failure shows on the screen and can be retried. A build with the
 * Japanese assets adds a Language row (left/right picks it, remembered). Settings
 * live in online.cfg in the working directory, next to the save.
 *
 * main.c shows it in a window when the build has relay support and no session,
 * script or test flags were given (--launcher forces it, for tests).
 */

#include <stdbool.h>

#include "net/net.h"

typedef enum { LAUNCH_PLAY, LAUNCH_ONLINE, LAUNCH_QUIT } LaunchChoice;

/* Run the launcher until the player picks. LAUNCH_ONLINE: net_start succeeded
 * with *cfg (which then points into the launcher's own storage). It sets the
 * Locale from online.cfg unless `lang_given` (--lang / EB_LANG already set it). */
LaunchChoice launcher_run(NetConfig *cfg, bool lang_given);

/* online.cfg's relay, or NULL. */
const char *launcher_saved_relay(void);
/* Remember a Session's invite (for the next Join) and, when hosting, the relay. */
void launcher_remember(const char *relay, const char *invite);

#endif /* EB_NET_LAUNCHER_H */
