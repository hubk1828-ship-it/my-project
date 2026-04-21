#!/bin/bash
cd /home/drpcsa/repositories/my-project/frontend
export PORT=33441
export NODE_ENV=production
exec node_modules/.bin/next start -p 33441
