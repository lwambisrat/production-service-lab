#!/usr/bin/env bash
# Start all services in dependency order: C → B → A, then Nginx.
sudo systemctl start ride-dispatch driver-matching ride-booking nginx
