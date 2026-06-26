#!/usr/bin/env bash
# Restart all services in dependency order: C → B → A, then Nginx.
sudo systemctl restart ride-dispatch driver-matching ride-booking nginx
sleep 3
