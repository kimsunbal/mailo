> Part of the [mailo design notes](README.md).

# 4. CLI surface

```
mailo init [--from -]               create the config (~/.config/mailo/config.toml). See 6.3
                                    --from - : read an export line from stdin, non-interactive
mailo config set KEY [VALUE]        set one key; omit VALUE for secrets to be prompted. 6.3.3
mailo config get KEY                read one value (secrets masked; --reveal to unmask)
mailo config list                   print everything, secrets masked
mailo config unset KEY              remove a key
mailo config edit                   open it in $EDITOR
mailo config export [--no-secrets]  print the config as one line, for another machine. 6.3.7
mailo test [-c CHANNEL]             verify the config and send a test
mailo send -e EVENT -s SUBJECT [-b BODY] [-c CHANNEL] [--to ADDR]
                                    send directly; without -b, read stdin, else reuse the subject
mailo run [--name NAME] -- CMD...   wrap a command; exit code, duration, and a log tail attached
mailo hook                          hook entry point; reads JSON on stdin and branches itself
mailo install-hooks [--user|--project] [--events blocked,failed,done]
mailo uninstall-hooks
```

The old `mailer.py -s "..."` becomes `mailo send -s "..."` (`-e` defaults to `custom`).

`mailo hook` is a **single entry point.** It reads `hook_event_name` and
`notification_type` from the stdin JSON and branches on its own, so there is no
per-hook script and every settings.json entry `install-hooks` writes is the same
command.

## 4.1 What `mailo run` sends

```
$ mailo run --name train -- ./run-train.sh
```
On exit:
```
[workstation] ✅ train — done
  machine   workstation
  project   exp-042        <- the directory *name* only, never the full path (6.2)
  elapsed   2h 14m
  exit      0
  --- last 5 lines ---
  epoch 40 | loss 0.0231 | acc 0.981
  saved: ckpt/final.pt
```
A non-zero exit sends `failed` instead: `❌ train — failed (exit 137)`.
