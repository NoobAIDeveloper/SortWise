const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

const isDev = process.env.NODE_ENV !== 'production';

let win; // Keep a reference to the window object

function createWindow() {
  win = new BrowserWindow({
    width: 820,
    height: 620,
    minWidth: 680,
    minHeight: 500,
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  if (isDev) {
    win.loadURL('http://localhost:3000');
  } else {
    win.loadFile(path.join(__dirname, 'build', 'index.html'));
  }
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

ipcMain.handle('dialog:openDirectory', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    properties: ['openDirectory', 'multiSelections'],
  });
  if (canceled) {
    return;
  }
  return filePaths;
});

ipcMain.handle('sort:files', async (event, options) => {
  console.log('Received sort:files request with options:', options);
  return new Promise((resolve, reject) => {
    const backendPath = isDev
      ? path.join(__dirname, '../backend/main.py')
      : path.join(process.resourcesPath, 'main');

    const pythonExecutable = isDev ? path.join(__dirname, '../venv/bin/python') : backendPath;
    const python = spawn(pythonExecutable, isDev ? [backendPath, JSON.stringify(options)] : [JSON.stringify(options)]);

    let stdoutData = '';
    let stderrData = '';

    python.stdout.on('data', (data) => {
      const output = data.toString();
      console.log("Python stdout:", output);
      const lines = output.split('\n');
      for (const line of lines) {
        if (line.startsWith('{')) {
          try {
            const json = JSON.parse(line);
            if (json.type === 'progress') {
              win.webContents.send('sort:progress', json.value);
            } else {
              stdoutData += line + '\n';
            }
          } catch (e) {
            // Not a json line, just append
            stdoutData += line + '\n';
          }
        }
      }
    });

    python.stderr.on('data', (data) => {
      stderrData += data.toString();
    });

    python.on('close', (code) => {
      console.log(`Python process exited with code ${code}`);
      if (stderrData) {
        console.warn(`Stderr from Python script: ${stderrData}`);
      }

      if (code === 0) {
        try {
          const result = JSON.parse(stdoutData);
          resolve(result);
        } catch (e) {
          reject(new Error("Failed to parse final JSON from Python script."));
        }
      } else {
        reject(new Error(stderrData || `Python script failed with exit code ${code}`));
      }
    });
  });
});

ipcMain.handle('undo:sort', async (event, logFile) => {
  return new Promise((resolve, reject) => {
    const backendPath = isDev
      ? path.join(__dirname, '../backend/main.py')
      : path.join(process.resourcesPath, 'main');

    const pythonExecutable = isDev ? path.join(__dirname, '../venv/bin/python') : backendPath;
    const python = spawn(pythonExecutable, isDev ? [backendPath, 'undo', logFile] : ['undo', logFile]);

    let stdoutData = '';

    python.stdout.on('data', (data) => {
      stdoutData += data.toString();
    });

    python.on('close', (code) => {
      if (code === 0) {
        try {
          const result = JSON.parse(stdoutData);
          resolve(result);
        } catch (e) {
          reject(new Error("Failed to parse final JSON from Python script."));
        }
      } else {
        reject(new Error(`Python script failed with exit code ${code}`));
      }
    });
  });
});
