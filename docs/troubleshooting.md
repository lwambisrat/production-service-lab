# Troubleshooting Guide

## 1. Service not starting

Check:

```bash
systemctl status service-a
journalctl -u service-a -n 50
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
sudo systemctl restart service-a
```

---

## 3. Service dependency failure

Check:

```bash
systemctl status service-b
systemctl status service-c
```

If B or C is down:

A may fail.

Fix:

Start dependency first.

---

## 4. Service discovery failure

Check:

```bash
cat /etc/hosts
getent hosts service-b.internal
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
curl http://service-b.internal:3002/health
curl http://service-c.internal:3003/health
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
journalctl -u service-a -n 20
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
systemctl status service-a service-b service-c nginx
```

Expected:

All active.
