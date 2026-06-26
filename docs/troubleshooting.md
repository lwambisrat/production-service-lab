# Troubleshooting Guide

## 1. Service not starting

Check:

```bash
systemctl status ride-booking
journalctl -u ride-booking -n 50
```

Possible causes:

* syntax error
* wrong path
* missing dependency

---

## 2. Port conflict

Check:

```bash
sudo ss -tulpn
```

Problem:

Port already in use.

Fix:

```bash
sudo pkill -f uvicorn
```

Restart:

```bash
sudo systemctl restart ride-booking
```

---

## 3. Service dependency failure

Check:

```bash
systemctl status driver-matching
systemctl status ride-dispatch
```

If driver-matching or ride-dispatch is down:

A may fail.

Fix:

Start dependency first.

---

## 4. Service discovery failure

Check:

```bash
cat /etc/hosts
getent hosts driver-matching.internal
```

Problem:

Name resolution fails.

Fix:

Correct /etc/hosts.

---

## 5. Nginx failure

Check:

```bash
sudo nginx -t
sudo systemctl status nginx
```

Problem:

Config syntax issue.

Fix:

Correct config and reload.

---

## 6. Reverse proxy routing failure

Check:

```bash
sudo nginx -T
```

Problem:

Wrong route mapping.

Fix:

Correct location blocks.

---

## 7. Internal communication failure

Check:

```bash
curl http://driver-matching.internal:3002/health
curl http://ride-dispatch.internal:3003/health
```

Problem:

Service unreachable.

Fix:

Check service and network.

---

## 8. Missing logs

Check:

```bash
journalctl -xe
```

Problem:

Process crashed.

Fix:

Read crash logs.

---

## 9. Invalid route handling

Expected:

HTTP 404

Check logs:

```bash
journalctl -u ride-booking -n 20
```

Expected log:

route_not_found

---

## 10. Reboot recovery

Test:

```bash
sudo reboot
```

After reboot:

```bash
systemctl status ride-booking driver-matching ride-dispatch nginx
```

Expected:

All active.
