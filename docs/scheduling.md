# Scheduling Forecast Collection

The `omni-weather` CLI fetches one forecast, optionally writes it to SQLite,
and exits. Use an operating-system scheduler to collect forecasts regularly.
Reusing the same SQLite path is expected: every invocation creates a new row in
`forecast_runs` and stores its provider results under that run.

## Automatic daily setup

After writing a configuration, `omni-weather init` offers to install automatic
daily collection at a chosen local time (default `06:00`). It uses the current
Python environment and the scheduler native to the host:

| Platform | Managed scheduler |
|----------|-------------------|
| Linux | Current user's crontab |
| macOS | Per-user launchd LaunchAgent |
| Windows | Current user's Task Scheduler job |

Jobs have stable identifiers derived from the absolute config path, so separate
configs can have separate schedules. Re-running `init` for a config replaces
its managed job. Scheduler output is written to the platform's user log
directory where the backend supports redirection.

Run `omni-weather doctor --config /absolute/path/to/config.toml` to verify the
job. A missing, inactive, stale, or cross-platform schedule is shown as a
warning and does not change an otherwise successful doctor exit code.

The manual examples below run once per hour and are useful for custom cadences.
Replace every `/absolute/path/...` value with the appropriate path on the host;
schedulers should not rely on relative paths or shell aliases.

## Before scheduling

Run the exact command interactively first:

```bash
cd /absolute/path/to/omni-weather-forecast-apis
/absolute/path/to/uv run omni-weather \
  --config /absolute/path/to/config.toml \
  --sqlite /absolute/path/to/forecasts.sqlite
```

Find the paths needed in the examples with:

```bash
command -v uv
pwd
```

Use absolute paths for the configuration, database, and log files. The user
running the scheduled job must be able to read the configuration and write to
the database and log directory.

If the configuration references API keys with `${ENVIRONMENT_VARIABLE}`
placeholders, remember that cron and launchd do not normally load variables
from an interactive shell profile. Supply them explicitly as described in each
platform section. Do not commit secrets to the repository.

## Linux: cron

Open the current user's crontab:

```bash
crontab -e
```

Add an entry like this, keeping the command on one line:

```cron
# Fetch forecasts at the start of every hour.
0 * * * * cd /absolute/path/to/omni-weather-forecast-apis && /absolute/path/to/uv run omni-weather --config /absolute/path/to/config.toml --sqlite /absolute/path/to/forecasts.sqlite >> /absolute/path/to/omni-weather-cron.log 2>&1
```

The five schedule fields are minute, hour, day of month, month, and day of
week. Some common schedules are:

| Schedule | Meaning |
|----------|---------|
| `*/15 * * * *` | Every 15 minutes |
| `0 * * * *` | Every hour |
| `0 */6 * * *` | Every 6 hours |
| `0 0 * * *` | Daily at midnight |

Cron uses a minimal environment. If the config uses environment-variable
placeholders, define those variables above the job in the crontab or invoke a
wrapper script that loads them from a protected file. For example:

```cron
OPENWEATHER_API_KEY=replace-with-the-real-value
0 * * * * cd /absolute/path/to/omni-weather-forecast-apis && /absolute/path/to/uv run omni-weather --config /absolute/path/to/config.toml --sqlite /absolute/path/to/forecasts.sqlite >> /absolute/path/to/omni-weather-cron.log 2>&1
```

Restrict access to the crontab and any secret files according to the host's
security policy. Avoid putting secrets directly in the command because they
may be exposed through process listings or shell history.

Cron can start a new invocation while an earlier one is still running. On
Linux systems with `flock`, prevent overlaps with:

```cron
0 * * * * /usr/bin/flock -n /absolute/path/to/omni-weather.lock /bin/sh -c 'cd /absolute/path/to/omni-weather-forecast-apis && exec /absolute/path/to/uv run omni-weather --config /absolute/path/to/config.toml --sqlite /absolute/path/to/forecasts.sqlite' >> /absolute/path/to/omni-weather-cron.log 2>&1
```

Check the installed entry and watch its output:

```bash
crontab -l
tail -f /absolute/path/to/omni-weather-cron.log
```

To stop the job, run `crontab -e` and remove its line. Cron generally does not
run jobs missed while the computer is powered off or asleep.

## macOS: launchd

Create `~/Library/LaunchAgents/io.github.hbmartin.omni-weather.plist` with the
following contents. Replace every path before loading it.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>io.github.hbmartin.omni-weather</string>

  <key>ProgramArguments</key>
  <array>
    <string>/absolute/path/to/uv</string>
    <string>run</string>
    <string>omni-weather</string>
    <string>--config</string>
    <string>/absolute/path/to/config.toml</string>
    <string>--sqlite</string>
    <string>/absolute/path/to/forecasts.sqlite</string>
  </array>

  <key>WorkingDirectory</key>
  <string>/absolute/path/to/omni-weather-forecast-apis</string>

  <key>StartInterval</key>
  <integer>3600</integer>

  <key>RunAtLoad</key>
  <true/>

  <key>StandardOutPath</key>
  <string>/absolute/path/to/omni-weather-launchd.log</string>
  <key>StandardErrorPath</key>
  <string>/absolute/path/to/omni-weather-launchd.error.log</string>
</dict>
</plist>
```

`StartInterval` is expressed in seconds; `3600` means once per hour. launchd
does not start a second copy of the same job while its previous invocation is
still running.

If the config uses environment-variable placeholders, add an
`EnvironmentVariables` dictionary inside the top-level `<dict>`:

```xml
<key>EnvironmentVariables</key>
<dict>
  <key>OPENWEATHER_API_KEY</key>
  <string>replace-with-the-real-value</string>
</dict>
```

Because this stores the value in the plist, limit access to the file:

```bash
chmod 600 "$HOME/Library/LaunchAgents/io.github.hbmartin.omni-weather.plist"
```

Validate and load the agent:

```bash
plutil -lint "$HOME/Library/LaunchAgents/io.github.hbmartin.omni-weather.plist"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/io.github.hbmartin.omni-weather.plist"
```

`RunAtLoad` requests an immediate first run. Trigger another run manually and
inspect its status and logs with:

```bash
launchctl kickstart -k \
  "gui/$(id -u)/io.github.hbmartin.omni-weather"
launchctl print "gui/$(id -u)/io.github.hbmartin.omni-weather"
tail -f /absolute/path/to/omni-weather-launchd.error.log
```

After editing an already loaded plist, unload and bootstrap it again. To stop
and unload the agent:

```bash
launchctl bootout \
  "gui/$(id -u)/io.github.hbmartin.omni-weather"
```

A LaunchAgent runs only while that user is logged in. For unattended,
machine-wide collection, use a LaunchDaemon in `/Library/LaunchDaemons` with a
dedicated service account and appropriately protected configuration instead.

## Confirming collection

After at least one scheduled interval, confirm that new runs are being saved:

```bash
sqlite3 /absolute/path/to/forecasts.sqlite \
  'SELECT id, completed_at, latitude, longitude FROM forecast_runs ORDER BY id DESC LIMIT 5;'
```

Also monitor the scheduler's stdout and stderr files. The CLI exits with `0`
when every provider succeeds, `1` when one or more providers fail, and `2` for
invalid arguments or configuration errors.
