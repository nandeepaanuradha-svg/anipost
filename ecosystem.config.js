// PM2 manages one Python polling process. No npm dependencies are needed here.
const path = require('path');
module.exports = {
  apps: [{
    name: 'anipost',
    cwd: __dirname,
    script: path.join(__dirname, 'bot.py'),
    interpreter: path.join(__dirname, '.venv', 'bin', 'python'),
    exec_mode: 'fork',
    instances: 1,
    autorestart: true,
    watch: false,
    restart_delay: 5000,
    min_uptime: '30s',
    max_restarts: 10,
    kill_timeout: 15000,
    time: true,
    env: { PYTHONUNBUFFERED: '1' }
  }]
};
