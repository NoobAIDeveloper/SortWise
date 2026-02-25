import React, { useState, useEffect } from 'react';
import './App.css';

function Toggle({ name, checked, onChange }) {
  return (
    <label className="toggle">
      <input type="checkbox" name={name} checked={checked} onChange={onChange} />
      <span className="toggle-slider" />
    </label>
  );
}

function App() {
  const [folders, setFolders] = useState([]);
  const [sortOptions, setSortOptions] = useState({
    exifDate: true,
    cameraModel: true,
    fileType: true,
    location: false,
    orientation: false,
    livePhotos: false,
    deduplication: false,
  });
  const [fileOperation, setFileOperation] = useState('move');
  const [conflictResolution, setConflictResolution] = useState('rename');
  const [progress, setProgress] = useState(0);
  const [logFile, setLogFile] = useState(null);
  const [dateSortOption, setDateSortOption] = useState('yearMonth');
  const [isSorting, setIsSorting] = useState(false);
  const [status, setStatus] = useState(null); // { message, type: 'success' | 'error' }

  useEffect(() => {
    window.electronAPI.onSortProgress((event, value) => {
      setProgress(value);
    });
  }, []);

  const handleAddFolders = async () => {
    const result = await window.electronAPI.selectFolders();
    if (result) {
      setFolders(prev => [...new Set([...prev, ...result])]);
    }
  };

  const handleRemoveFolder = (index) => {
    setFolders(prev => prev.filter((_, i) => i !== index));
  };

  const handleCheckboxChange = (event) => {
    const { name, checked } = event.target;
    setSortOptions(prev => ({ ...prev, [name]: checked }));
  };

  const handleSort = async () => {
    if (folders.length === 0) {
      setStatus({ message: 'Please add at least one folder to sort.', type: 'error' });
      return;
    }
    if (!Object.values(sortOptions).some(Boolean)) {
      setStatus({ message: 'Please enable at least one sorting option.', type: 'error' });
      return;
    }

    setIsSorting(true);
    setStatus(null);
    setProgress(0);

    try {
      const result = await window.electronAPI.sortFiles({
        folders,
        sortOptions,
        dateSortOption,
        fileOperation,
        conflictResolution,
      });
      setLogFile(result.logFile);
      setStatus({ message: result.message, type: 'success' });
    } catch (e) {
      setStatus({ message: e.message || 'An error occurred while sorting.', type: 'error' });
    } finally {
      setIsSorting(false);
      setProgress(0);
    }
  };

  const handleUndoSort = async () => {
    if (!logFile) return;
    try {
      const result = await window.electronAPI.undoSort(logFile);
      setLogFile(null);
      setStatus({ message: result.message, type: result.status === 'success' ? 'success' : 'error' });
    } catch (e) {
      setStatus({ message: e.message || 'Undo failed.', type: 'error' });
    }
  };

  const sortRows = [
    { name: 'exifDate',      label: 'EXIF Date' },
    { name: 'cameraModel',   label: 'Camera Model' },
    { name: 'fileType',      label: 'File Type' },
    { name: 'location',      label: 'Location' },
    { name: 'orientation',   label: 'Orientation' },
    { name: 'livePhotos',    label: 'Live Photos' },
    { name: 'deduplication', label: 'Deduplication' },
  ];

  return (
    <div className="app">
      {/* Title bar — draggable, traffic lights inset here by macOS */}
      <div className="titlebar">
        <span className="app-title">SortWise</span>
      </div>

      <div className="main-layout">
        {/* Sidebar — folder management */}
        <aside className="sidebar">
          <div className="sidebar-section-label">Source Folders</div>
          <button className="add-folder-btn" onClick={handleAddFolders}>
            <span>+</span> Add Folder
          </button>

          <div className="folder-list">
            {folders.length === 0 && (
              <p className="empty-hint">No folders selected.</p>
            )}
            {folders.map((folder, i) => {
              const parts = folder.split('/');
              const display = parts[parts.length - 1] || folder;
              return (
                <div key={folder} className="folder-item">
                  <span className="folder-icon">📁</span>
                  <span className="folder-path" title={folder}>{display}</span>
                  <button
                    className="remove-folder"
                    onClick={() => handleRemoveFolder(i)}
                    title="Remove folder"
                  >
                    ×
                  </button>
                </div>
              );
            })}
          </div>
        </aside>

        {/* Main content */}
        <main className="content">
          <div className="section-label">Sorting Options</div>
          <div className="card">
            {sortRows.map(({ name, label }) => (
              <div key={name} className="card-row">
                <div className="row-left">
                  <span className="row-label">{label}</span>
                  {name === 'exifDate' && sortOptions.exifDate && (
                    <select
                      className="date-select"
                      value={dateSortOption}
                      onChange={e => setDateSortOption(e.target.value)}
                    >
                      <option value="yearMonth">Year &amp; Month</option>
                      <option value="year">Year Only</option>
                    </select>
                  )}
                </div>
                <Toggle name={name} checked={sortOptions[name]} onChange={handleCheckboxChange} />
              </div>
            ))}
          </div>

          <div className="section-label">File Handling</div>
          <div className="card">
            <div className="card-row">
              <span className="row-label">Operation</span>
              <div className="radio-group">
                {[['move', 'Move Files'], ['copy', 'Copy Files']].map(([val, lbl]) => (
                  <label
                    key={val}
                    className={`radio-option${fileOperation === val ? ' selected' : ''}`}
                  >
                    <input
                      type="radio"
                      name="fileOperation"
                      value={val}
                      checked={fileOperation === val}
                      onChange={e => setFileOperation(e.target.value)}
                    />
                    {lbl}
                  </label>
                ))}
              </div>
            </div>
            <div className="card-row">
              <span className="row-label">Conflicts</span>
              <div className="radio-group">
                {[['rename', 'Rename'], ['overwrite', 'Overwrite']].map(([val, lbl]) => (
                  <label
                    key={val}
                    className={`radio-option${conflictResolution === val ? ' selected' : ''}`}
                  >
                    <input
                      type="radio"
                      name="conflictResolution"
                      value={val}
                      checked={conflictResolution === val}
                      onChange={e => setConflictResolution(e.target.value)}
                    />
                    {lbl}
                  </label>
                ))}
              </div>
            </div>
          </div>

          {isSorting && (
            <div className="progress-section">
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${progress}%` }} />
              </div>
              <span className="progress-text">{progress}%</span>
            </div>
          )}

          {status && (
            <div className={`status-message ${status.type}`}>{status.message}</div>
          )}

          <div className="actions">
            <button
              className="btn-secondary"
              onClick={handleUndoSort}
              disabled={!logFile || isSorting}
            >
              ↩ Undo Last Sort
            </button>
            <button className="btn-primary" onClick={handleSort} disabled={isSorting}>
              {isSorting ? 'Sorting…' : 'Sort Files ▶'}
            </button>
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
