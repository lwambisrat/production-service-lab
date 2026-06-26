#!/usr/bin/env bash
# Stop all services. ride-booking is stopped first since driver-matching and ride-dispatch are its dependencies.
sudo systemctl stop ride-booking driver-matching ride-dispatch nginx
