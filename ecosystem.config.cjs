module.exports = {
  apps: [
    {
      name: 'kiosk-backend',
      cwd: './backend',
      script: 'uvicorn',
      args: 'main:app --host 0.0.0.0 --port 8000',
      interpreter: 'python3',
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      watch: false,
    },
    {
      name: 'kiosk-frontend',
      cwd: './frontend',
      script: 'npx',
      args: 'serve dist -s -l 5173 --no-clipboard -L',
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      watch: false,
    },
  ],
};
