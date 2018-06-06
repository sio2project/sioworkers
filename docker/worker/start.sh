#!/bin/bash
cat /vpn/resolv.conf > /etc/resolv.conf
sudo -u appuser -E bash -c "HOME=/spr4g/ ./supervisor.sh startfg"
