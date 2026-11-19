// =========================================================
// script.js - Vanilla JS for Face Attendance System
// Supports Active Class Sessions, Real-Time Logs, Manual Attendance & Admin
// =========================================================

// Global application state
let currentUser = null;
let webcamStream = null;
let isCameraRunning = false;
let frameInterval = null;
let autoRefreshTimer = null;
let isAutoRefreshActive = true;
let allStudents = [];
let allBatches = ["Batch A", "Batch B"];
let enrollingPhotoBase64 = null;
let currentServerDate = getLocalDateStr();

// Default active class session
let activeSession = {
  batch: "Batch A",
  room_no: "Room 101",
  class_time: "09:00 AM - 10:00 AM"
};

// Local date string helper (year-month-day in user's local timezone)
function getLocalDateStr() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

// Global Toast helper
function showToast(message, type = "success") {
  const toast = document.getElementById("global-toast");
  if (!toast) return;

  toast.textContent = message;
  toast.className = `toast toast-${type}`;
  toast.style.display = "block";

  setTimeout(() => {
    toast.style.display = "none";
  }, 3500);
}

// Initialize app when DOM loads
window.addEventListener("DOMContentLoaded", () => {
  // Sync with server date first to avoid any timezone discrepancies
  fetchServerDate();

  // Restore saved active class session if available
  const savedSession = localStorage.getItem("active_class_session");
  if (savedSession) {
    try {
      activeSession = JSON.parse(savedSession);
    } catch (e) {
      console.error("Error parsing saved session:", e);
    }
  }

  // Restore saved login session
  const savedUser = localStorage.getItem("attendance_user");
  if (savedUser) {
    try {
      currentUser = JSON.parse(savedUser);
      showDashboard();
    } catch (e) {
      localStorage.removeItem("attendance_user");
    }
  }

  // Set today's date in filters
  const dateInput = document.getElementById("filter-date");
  if (dateInput) dateInput.value = currentServerDate;

  const manualDateInput = document.getElementById("manual-entry-date");
  if (manualDateInput) manualDateInput.value = currentServerDate;

  // Load initial data
  loadBatches();
  loadStudents();
  loadAttendance();

  // Start real-time background sync
  startAutoRefresh();
});

// Fetch backend server date
function fetchServerDate() {
  fetch("/api/server-date")
    .then(res => res.json())
    .then(data => {
      if (data && data.date) {
        currentServerDate = data.date;
        const dateInput = document.getElementById("filter-date");
        if (dateInput && !dateInput.value) dateInput.value = currentServerDate;
        const manualDateInput = document.getElementById("manual-entry-date");
        if (manualDateInput && !manualDateInput.value) manualDateInput.value = currentServerDate;
      }
    })
    .catch(err => {
      console.log("Using browser local date:", currentServerDate);
    });
}

// =========================================================
// 1. ACTIVE CLASS SESSION CONTROLS
// =========================================================

function onSessionBatchChange() {
  const select = document.getElementById("session-batch-select");
  const customInput = document.getElementById("session-batch-custom");

  if (select.value === "custom") {
    customInput.style.display = "block";
    customInput.focus();
  } else {
    customInput.style.display = "none";
    updateActiveSession();
  }
}

function onSessionTimeChange() {
  const select = document.getElementById("session-time-select");
  const customInput = document.getElementById("session-time-custom");

  if (select.value === "custom") {
    customInput.style.display = "block";
    customInput.focus();
  } else {
    customInput.style.display = "none";
    updateActiveSession();
  }
}

function updateActiveSession() {
  const batchSelect = document.getElementById("session-batch-select");
  const batchCustom = document.getElementById("session-batch-custom");
  const roomInput = document.getElementById("session-room-input");
  const timeSelect = document.getElementById("session-time-select");
  const timeCustom = document.getElementById("session-time-custom");

  let batch = batchSelect ? batchSelect.value : "Batch A";
  if (batch === "custom" && batchCustom && batchCustom.value.trim()) {
    batch = batchCustom.value.trim();
  }

  let room = roomInput && roomInput.value.trim() ? roomInput.value.trim() : "Room 101";

  let time = timeSelect ? timeSelect.value : "09:00 AM - 10:00 AM";
  if (time === "custom" && timeCustom && timeCustom.value.trim()) {
    time = timeCustom.value.trim();
  }

  activeSession = {
    batch: batch,
    room_no: room,
    class_time: time
  };

  localStorage.setItem("active_class_session", JSON.stringify(activeSession));

  // Update UI indicators across all tabs
  const badge = document.getElementById("session-badge");
  if (badge) badge.textContent = `Active: ${batch} • ${room} • ${time}`;

  const webcamPill = document.getElementById("webcam-session-pill");
  if (webcamPill) webcamPill.textContent = `Session: ${batch} • ${room}`;

  const manualPill = document.getElementById("manual-session-pill");
  if (manualPill) manualPill.textContent = `Active: ${batch} • ${room}`;

  const uploadPill = document.getElementById("upload-session-pill");
  if (uploadPill) uploadPill.textContent = `Session: ${batch} • ${room}`;

  syncManualFormWithSession();
}

function syncSessionInputs() {
  const batchSelect = document.getElementById("session-batch-select");
  const roomInput = document.getElementById("session-room-input");
  const timeSelect = document.getElementById("session-time-select");

  if (roomInput) roomInput.value = activeSession.room_no || "Room 101";

  if (batchSelect) {
    let found = false;
    for (let i = 0; i < batchSelect.options.length; i++) {
      if (batchSelect.options[i].value === activeSession.batch) {
        batchSelect.selectedIndex = i;
        found = true;
        break;
      }
    }
    if (!found) {
      batchSelect.value = "custom";
      const customInput = document.getElementById("session-batch-custom");
      if (customInput) {
        customInput.style.display = "block";
        customInput.value = activeSession.batch;
      }
    }
  }

  if (timeSelect) {
    let found = false;
    for (let i = 0; i < timeSelect.options.length; i++) {
      if (timeSelect.options[i].value === activeSession.class_time) {
        timeSelect.selectedIndex = i;
        found = true;
        break;
      }
    }
    if (!found) {
      timeSelect.value = "custom";
      const customInput = document.getElementById("session-time-custom");
      if (customInput) {
        customInput.style.display = "block";
        customInput.value = activeSession.class_time;
      }
    }
  }

  updateActiveSession();
}

function syncManualFormWithSession() {
  const batchInput = document.getElementById("manual-entry-batch");
  const roomInput = document.getElementById("manual-entry-room");
  const timeInput = document.getElementById("manual-entry-time");

  if (batchInput) batchInput.value = activeSession.batch || "Batch A";
  if (roomInput) roomInput.value = activeSession.room_no || "Room 101";
  if (timeInput) timeInput.value = activeSession.class_time || "09:00 AM - 10:00 AM";
}

// =========================================================
// 2. AUTHENTICATION (LOGIN & LOGOUT)
// =========================================================

function handleLogin() {
  const usernameInput = document.getElementById("username");
  const passwordInput = document.getElementById("password");
  const errorDiv = document.getElementById("login-error");

  const username = usernameInput.value.trim();
  const password = passwordInput.value.trim();

  if (!username || !password) {
    errorDiv.textContent = "Please enter both username and password!";
    errorDiv.style.display = "block";
    return;
  }

  errorDiv.style.display = "none";

  fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: username, password: password })
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        currentUser = {
          username: username,
          role: data.role,
          name: data.name
        };
        localStorage.setItem("attendance_user", JSON.stringify(currentUser));
        showDashboard();
        showToast(`Welcome back, ${data.name}!`, "success");
      } else {
        errorDiv.textContent = data.message || "Invalid login credentials!";
        errorDiv.style.display = "block";
      }
    })
    .catch(err => {
      errorDiv.textContent = "Error connecting to server. Is the application running?";
      errorDiv.style.display = "block";
    });
}

function quickFill(user, pass) {
  document.getElementById("username").value = user;
  document.getElementById("password").value = pass;
  document.getElementById("login-error").style.display = "none";
}

function logout() {
  stopCamera();
  currentUser = null;
  localStorage.removeItem("attendance_user");
  document.getElementById("login-section").style.display = "block";
  document.getElementById("dashboard-section").style.display = "none";
  document.getElementById("user-info").style.display = "none";

  const adminTabBtn = document.getElementById("tab-btn-admin");
  if (adminTabBtn) adminTabBtn.style.display = "none";

  showTab("webcam");
  showToast("Logged out successfully.", "info");
}

function showDashboard() {
  document.getElementById("login-section").style.display = "none";
  document.getElementById("dashboard-section").style.display = "block";
  document.getElementById("user-info").style.display = "flex";
  document.getElementById("user-display").textContent = `${currentUser.name} (${currentUser.role.toUpperCase()})`;

  const adminTabBtn = document.getElementById("tab-btn-admin");
  if (adminTabBtn) {
    adminTabBtn.style.display = (currentUser.role === "admin") ? "inline-block" : "none";
  }

  syncSessionInputs();
  loadBatches();
  loadAttendance();
  loadStudents();
}

// =========================================================
// 3. TABS NAVIGATION
// =========================================================

function showTab(tabName) {
  if (tabName === "admin" && (!currentUser || currentUser.role !== "admin")) {
    alert("Access Denied: Only administrators can access the Admin Panel.");
    return;
  }

  const tabs = ["webcam", "manual", "attendance", "upload", "students", "admin"];
  tabs.forEach(t => {
    const el = document.getElementById("tab-" + t);
    if (el) el.style.display = (t === tabName) ? "block" : "none";

    const btn = document.getElementById("tab-btn-" + t);
    if (btn) {
      if (t === tabName) btn.classList.add("active");
      else btn.classList.remove("active");
    }
  });

  if (tabName === "attendance") {
    loadAttendance();
  } else if (tabName === "manual") {
    syncManualFormWithSession();
    renderManualRosterTable();
  } else if (tabName === "students") {
    loadStudents();
  } else if (tabName === "admin") {
    adminLoadStudentsTable();
    loadBatches();
  }
}

// =========================================================
// 4. WEBCAM CONTROLS & REAL-TIME FACE RECOGNITION
// =========================================================

function toggleCamera() {
  if (isCameraRunning) {
    stopCamera();
  } else {
    startCamera();
  }
}

function startCamera() {
  const video = document.getElementById("webcam-video");
  const cameraBtn = document.getElementById("camera-toggle-btn");
  const statusBadge = document.getElementById("camera-status");
  const msgBox = document.getElementById("status-message");

  msgBox.style.display = "none";

  navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
    .then(stream => {
      webcamStream = stream;
      video.srcObject = stream;
      isCameraRunning = true;

      cameraBtn.textContent = "Stop Camera";
      cameraBtn.className = "btn btn-danger";
      statusBadge.textContent = "Camera Live";
      statusBadge.className = "status-badge active";

      // Process a frame every 1.2 seconds
      frameInterval = setInterval(captureAndSendFrame, 1200);
      showToast("Webcam active. Face recognition started.", "info");
    })
    .catch(err => {
      alert("Could not access webcam: " + err.message);
    });
}

function stopCamera() {
  const video = document.getElementById("webcam-video");
  const cameraBtn = document.getElementById("camera-toggle-btn");
  const statusBadge = document.getElementById("camera-status");
  const canvas = document.getElementById("overlay-canvas");

  if (frameInterval) {
    clearInterval(frameInterval);
    frameInterval = null;
  }

  if (webcamStream) {
    webcamStream.getTracks().forEach(track => track.stop());
    webcamStream = null;
  }

  if (video) video.srcObject = null;
  isCameraRunning = false;

  if (cameraBtn) {
    cameraBtn.textContent = "Start Camera";
    cameraBtn.className = "btn btn-success";
  }
  if (statusBadge) {
    statusBadge.textContent = "Camera Off";
    statusBadge.className = "status-badge";
  }

  if (canvas) {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
}

function captureAndSendFrame() {
  if (!isCameraRunning) return;

  const video = document.getElementById("webcam-video");
  if (!video || video.videoWidth === 0) return;

  const tempCanvas = document.createElement("canvas");
  tempCanvas.width = video.videoWidth;
  tempCanvas.height = video.videoHeight;
  const ctx = tempCanvas.getContext("2d");
  ctx.drawImage(video, 0, 0);

  const base64Image = tempCanvas.toDataURL("image/jpeg", 0.8);

  fetch("/api/recognize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      image: base64Image,
      batch: activeSession.batch,
      room_no: activeSession.room_no,
      class_time: activeSession.class_time
    })
  })
    .then(res => res.json())
    .then(data => {
      drawDetections(data.detections || []);
    })
    .catch(err => {
      console.log("Recognition error:", err);
    });
}

function drawDetections(detections) {
  const canvas = document.getElementById("overlay-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const msgBox = document.getElementById("status-message");

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (detections.length === 0) {
    return;
  }

  let statusHtml = [];
  let hasNewRecognition = false;

  detections.forEach(det => {
    const [x1, y1, x2, y2] = det.box;
    const w = x2 - x1;
    const h = y2 - y1;

    const isRec = det.recognized;
    const color = isRec ? "#10b981" : "#ef4444";
    const label = isRec ? `${det.name} (${det.confidence}%)` : "Unknown";

    // Draw bounding box
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.strokeRect(x1, y1, w, h);

    // Draw label header
    ctx.fillStyle = color;
    ctx.font = "bold 14px Arial";
    const textWidth = ctx.measureText(label).width;
    ctx.fillRect(x1, Math.max(0, y1 - 22), textWidth + 10, 22);

    // Draw label text
    ctx.fillStyle = "#ffffff";
    ctx.fillText(label, x1 + 5, Math.max(16, y1 - 6));

    if (isRec) {
      statusHtml.push(`Recognized <strong>${det.name}</strong> (${det.confidence}%) — Logged PRESENT for <strong>${activeSession.batch}</strong> in <strong>${activeSession.room_no}</strong> (${activeSession.class_time})`);
      hasNewRecognition = true;
    }
  });

  if (statusHtml.length > 0) {
    msgBox.innerHTML = statusHtml.join("<br>");
    msgBox.style.display = "block";
    if (hasNewRecognition) {
      loadAttendance(); // Live update of attendance records!
    }
  }
}

// =========================================================
// 5. REAL-TIME AUTO REFRESH SYNC
// =========================================================

function toggleAutoRefresh() {
  isAutoRefreshActive = !isAutoRefreshActive;
  const btn = document.getElementById("btn-toggle-autorefresh");
  if (btn) {
    if (isAutoRefreshActive) {
      btn.textContent = "Auto-Refresh: ON (2s)";
      btn.className = "btn btn-small btn-success";
      showToast("Live auto-refresh enabled.", "info");
    } else {
      btn.textContent = "Auto-Refresh: OFF";
      btn.className = "btn btn-small btn-secondary";
      showToast("Auto-refresh paused.", "info");
    }
  }
}

function startAutoRefresh() {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer);
  // Auto-refresh every 2.5 seconds silently
  autoRefreshTimer = setInterval(() => {
    if (isAutoRefreshActive) {
      // Silently refresh attendance data
      loadAttendance(true);
    }
  }, 2500);
}

// =========================================================
// 6. ATTENDANCE RECORDS (VIEW, FILTER & REAL-TIME LOG)
// =========================================================

function onQuickDateChange() {
  const quickSelect = document.getElementById("filter-date-quick");
  const dateInput = document.getElementById("filter-date");

  if (quickSelect.value === "today") {
    dateInput.value = currentServerDate;
  } else if (quickSelect.value === "ALL") {
    dateInput.value = "";
  }
  loadAttendance();
}

function resetAttendanceFilters() {
  const dateInput = document.getElementById("filter-date");
  if (dateInput) dateInput.value = currentServerDate;

  const quickSelect = document.getElementById("filter-date-quick");
  if (quickSelect) quickSelect.value = "today";

  const batchFilter = document.getElementById("filter-batch");
  if (batchFilter) batchFilter.value = "ALL";

  const roomFilter = document.getElementById("filter-room");
  if (roomFilter) roomFilter.value = "";

  loadAttendance();
  showToast("Attendance filters reset to Today.", "info");
}

function loadAttendance(isSilent = false) {
  const dateInput = document.getElementById("filter-date");
  let dateVal = dateInput ? dateInput.value.trim() : "";

  // If date input is empty, default to "ALL"
  if (!dateVal) dateVal = "ALL";

  const batchVal = document.getElementById("filter-batch") ? document.getElementById("filter-batch").value : "ALL";
  const roomVal = document.getElementById("filter-room") ? document.getElementById("filter-room").value.trim() : "";

  let url = `/api/attendance?date=${encodeURIComponent(dateVal)}`;
  if (batchVal && batchVal !== "ALL") {
    url += `&batch=${encodeURIComponent(batchVal)}`;
  }
  if (roomVal) {
    url += `&room_no=${encodeURIComponent(roomVal)}`;
  }

  fetch(url)
    .then(res => res.json())
    .then(records => {
      renderAttendanceTable(records || []);
      renderLiveWebcamFeed(records || []);
    })
    .catch(err => {
      if (!isSilent) console.log("Could not load attendance:", err);
    });
}

function renderAttendanceTable(records) {
  const tbody = document.getElementById("attendance-tbody");
  if (!tbody) return;

  if (records.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align: center; color: #64748b; padding: 18px;">No attendance records found for selected filters.</td></tr>';
    return;
  }

  let html = "";
  records.forEach((r, idx) => {
    const isPresent = (r.status === "PRESENT");
    const statusColor = isPresent ? "#10b981" : "#ef4444";
    const toggleStatus = isPresent ? "ABSENT" : "PRESENT";
    const toggleBtnText = isPresent ? "Set Absent" : "Set Present";
    const toggleBtnClass = isPresent ? "btn btn-small btn-warning" : "btn btn-small btn-success";

    html += `
      <tr>
        <td>${idx + 1}</td>
        <td><strong>${r.student_id}</strong></td>
        <td>${r.name}</td>
        <td><span class="badge badge-neutral">${r.batch || "Batch A"}</span></td>
        <td>${r.room_no || "Room 101"}</td>
        <td>${r.class_time || "09:00 AM - 10:00 AM"}</td>
        <td>${r.date}</td>
        <td>${r.time}</td>
        <td><span style="color: ${statusColor}; font-weight: bold;">${r.status}</span></td>
        <td>
          <button class="${toggleBtnClass}" onclick="toggleRecordStatus(${r.id}, '${r.status}')">${toggleBtnText}</button>
          <button class="btn btn-small btn-danger" onclick="deleteRecord(${r.id})">Remove</button>
        </td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

function renderLiveWebcamFeed(records) {
  const liveTbody = document.getElementById("webcam-live-tbody");
  const countSpan = document.getElementById("live-count-today");

  if (countSpan) countSpan.textContent = records.length;
  if (!liveTbody) return;

  if (records.length === 0) {
    liveTbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #64748b; padding: 12px;">No attendance recorded yet.</td></tr>';
    return;
  }

  // Display top 15 most recent records
  const recentRecords = records.slice(0, 15);
  let html = "";
  recentRecords.forEach(r => {
    const isPresent = (r.status === "PRESENT");
    const statusBadge = isPresent
      ? '<span class="badge badge-success">PRESENT</span>'
      : '<span class="badge badge-neutral" style="color:#ef4444;">ABSENT</span>';

    html += `
      <tr>
        <td><strong>${r.time}</strong></td>
        <td>${r.name} <br><small style="color:#64748b;">${r.student_id}</small></td>
        <td>${r.batch}</td>
        <td>${statusBadge}</td>
      </tr>
    `;
  });
  liveTbody.innerHTML = html;
}

function toggleRecordStatus(recordId, currentStatus) {
  const newStatus = (currentStatus === "PRESENT") ? "ABSENT" : "PRESENT";

  fetch(`/api/attendance/${recordId}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: newStatus })
  })
    .then(res => res.json())
    .then(result => {
      showToast(result.message || `Updated status to ${newStatus}!`, "success");
      loadAttendance();
      loadStudents();
      renderManualRosterTable();
    })
    .catch(err => {
      showToast("Error updating status: " + err.message, "error");
    });
}

function deleteRecord(recordId) {
  if (!confirm("Are you sure you want to delete this attendance record?")) {
    return;
  }

  fetch("/api/attendance/" + recordId, {
    method: "DELETE"
  })
    .then(res => res.json())
    .then(result => {
      showToast("Attendance record removed.", "info");
      loadAttendance();
      loadStudents();
      renderManualRosterTable();
    })
    .catch(err => {
      showToast("Error deleting record: " + err.message, "error");
    });
}

// =========================================================
// 7. DEDICATED MANUAL ATTENDANCE FEATURE
// =========================================================

function submitDedicatedManualAttendance() {
  const studentSelect = document.getElementById("manual-entry-student");
  const statusSelect = document.getElementById("manual-entry-status");
  const batchInput = document.getElementById("manual-entry-batch");
  const roomInput = document.getElementById("manual-entry-room");
  const timeInput = document.getElementById("manual-entry-time");
  const dateInput = document.getElementById("manual-entry-date");
  const feedbackMsg = document.getElementById("manual-feedback-msg");

  const studentId = studentSelect ? studentSelect.value : "";
  const status = statusSelect ? statusSelect.value : "PRESENT";
  const batch = batchInput && batchInput.value.trim() ? batchInput.value.trim() : activeSession.batch;
  const room = roomInput && roomInput.value.trim() ? roomInput.value.trim() : activeSession.room_no;
  const time = timeInput && timeInput.value.trim() ? timeInput.value.trim() : activeSession.class_time;
  const date = dateInput && dateInput.value.trim() ? dateInput.value.trim() : currentServerDate;

  if (!studentId) {
    alert("Please select a student first!");
    return;
  }

  fetch("/api/attendance/mark", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      student_id: studentId,
      status: status,
      batch: batch,
      room_no: room,
      class_time: time,
      date: date
    })
  })
    .then(res => res.json())
    .then(result => {
      if (feedbackMsg) {
        feedbackMsg.className = "success-msg";
        feedbackMsg.innerHTML = `<strong>✓ Saved!</strong> ${result.message}`;
        feedbackMsg.style.display = "block";
      }

      showToast(result.message, "success");

      // Instantly refresh all views
      loadAttendance();
      loadStudents();
      renderManualRosterTable();
    })
    .catch(err => {
      if (feedbackMsg) {
        feedbackMsg.className = "error-msg";
        feedbackMsg.textContent = "Error saving attendance: " + err.message;
        feedbackMsg.style.display = "block";
      }
      showToast("Error saving attendance: " + err.message, "error");
    });
}

function quickMarkStudent(studentId, status) {
  fetch("/api/attendance/mark", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      student_id: studentId,
      status: status,
      batch: activeSession.batch,
      room_no: activeSession.room_no,
      class_time: activeSession.class_time,
      date: currentServerDate
    })
  })
    .then(res => res.json())
    .then(result => {
      showToast(result.message, (status === "PRESENT") ? "success" : "info");
      loadAttendance();
      loadStudents();
      renderManualRosterTable();
    })
    .catch(err => {
      showToast("Error updating attendance: " + err.message, "error");
    });
}

function renderManualRosterTable() {
  const batchFilter = document.getElementById("manual-roster-batch");
  const selectedBatch = batchFilter ? batchFilter.value : "ALL";
  const tbody = document.getElementById("manual-roster-tbody");
  if (!tbody) return;

  let filtered = allStudents;
  if (selectedBatch && selectedBatch !== "ALL") {
    filtered = allStudents.filter(s => s.batch === selectedBatch);
  }

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #64748b;">No students found for this batch.</td></tr>';
    return;
  }

  let html = "";
  filtered.forEach(s => {
    const status = s.today_status || "Not Marked";
    let statusStyle = "color: #64748b; font-weight: bold;";
    if (status === "PRESENT") statusStyle = "color: #10b981; font-weight: bold;";
    if (status === "ABSENT") statusStyle = "color: #ef4444; font-weight: bold;";

    html += `
      <tr>
        <td><strong>${s.student_id}</strong></td>
        <td>${s.name}</td>
        <td>${s.roll_no || "-"}</td>
        <td><span class="badge badge-neutral">${s.batch || "Batch A"}</span></td>
        <td><span style="${statusStyle}">${status}</span></td>
        <td>
          <button class="btn btn-small btn-success" onclick="quickMarkStudent('${s.student_id}', 'PRESENT')">Mark Present</button>
          <button class="btn btn-small btn-warning" onclick="quickMarkStudent('${s.student_id}', 'ABSENT')">Mark Absent</button>
        </td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

// =========================================================
// 8. REGISTERED STUDENTS DIRECTORY
// =========================================================

function loadBatches() {
  fetch("/api/batches")
    .then(res => res.json())
    .then(batches => {
      allBatches = batches || ["Batch A", "Batch B"];

      // 1. Session batch select
      const sessionSelect = document.getElementById("session-batch-select");
      if (sessionSelect) {
        let currentVal = activeSession.batch;
        let html = "";
        allBatches.forEach(b => {
          html += `<option value="${b}">${b}</option>`;
        });
        html += `<option value="custom">+ New Batch...</option>`;
        sessionSelect.innerHTML = html;
        if (allBatches.includes(currentVal)) {
          sessionSelect.value = currentVal;
        }
      }

      // 2. Attendance filter batch
      const filterBatch = document.getElementById("filter-batch");
      if (filterBatch) {
        let currentFilter = filterBatch.value;
        let html = `<option value="ALL">All Batches</option>`;
        allBatches.forEach(b => {
          html += `<option value="${b}">${b}</option>`;
        });
        filterBatch.innerHTML = html;
        if (currentFilter) filterBatch.value = currentFilter;
      }

      // 3. Registered students batch filter
      const studentBatchFilter = document.getElementById("student-batch-filter");
      if (studentBatchFilter) {
        let currentVal = studentBatchFilter.value;
        let html = `<option value="ALL">All Batches</option>`;
        allBatches.forEach(b => {
          html += `<option value="${b}">${b}</option>`;
        });
        studentBatchFilter.innerHTML = html;
        if (currentVal) studentBatchFilter.value = currentVal;
      }

      // 4. Manual roster batch filter
      const manualRosterBatch = document.getElementById("manual-roster-batch");
      if (manualRosterBatch) {
        let currentVal = manualRosterBatch.value;
        let html = `<option value="ALL">All Batches</option>`;
        allBatches.forEach(b => {
          html += `<option value="${b}">${b}</option>`;
        });
        manualRosterBatch.innerHTML = html;
        if (currentVal) manualRosterBatch.value = currentVal;
      }

      // 5. Admin suggestions datalist
      const datalist = document.getElementById("batch-suggestions");
      if (datalist) {
        let html = "";
        allBatches.forEach(b => {
          html += `<option value="${b}">`;
        });
        datalist.innerHTML = html;
      }
    })
    .catch(err => console.log("Error loading batches:", err));
}

function loadStudents() {
  const filterBatchEl = document.getElementById("student-batch-filter");
  const selectedBatch = filterBatchEl ? filterBatchEl.value : "ALL";

  let url = "/api/students";
  if (selectedBatch && selectedBatch !== "ALL") {
    url += `?batch=${encodeURIComponent(selectedBatch)}`;
  }

  fetch(url)
    .then(res => res.json())
    .then(students => {
      allStudents = students || [];
      const tbody = document.getElementById("students-tbody");
      const manualEntrySelect = document.getElementById("manual-entry-student");

      let tableHtml = "";
      let selectHtml = "";

      if (allStudents.length === 0) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#64748b;">No students found in this batch.</td></tr>';
        return;
      }

      allStudents.forEach(s => {
        const status = s.today_status || "Not Marked";
        let statusStyle = "color: #64748b; font-weight: bold;";
        if (status === "PRESENT") statusStyle = "color: #10b981; font-weight: bold;";
        if (status === "ABSENT") statusStyle = "color: #ef4444; font-weight: bold;";

        const faceBadge = s.has_face
          ? '<span class="badge badge-success">✓ Enrolled</span>'
          : '<span class="badge badge-neutral">No Face</span>';

        tableHtml += `
          <tr>
            <td><strong>${s.student_id}</strong></td>
            <td>${s.name}</td>
            <td>${s.roll_no || "-"}</td>
            <td><span class="badge badge-neutral">${s.batch || "Batch A"}</span></td>
            <td>${faceBadge}</td>
            <td><span style="${statusStyle}">${status}</span></td>
            <td>
              <button class="btn btn-small btn-success" onclick="quickMarkStudent('${s.student_id}', 'PRESENT')">Present</button>
              <button class="btn btn-small btn-warning" onclick="quickMarkStudent('${s.student_id}', 'ABSENT')">Absent</button>
            </td>
          </tr>
        `;

        selectHtml += `<option value="${s.student_id}">${s.name} (${s.student_id} - ${s.batch})</option>`;
      });

      if (tbody) tbody.innerHTML = tableHtml;
      if (manualEntrySelect) manualEntrySelect.innerHTML = selectHtml;

      renderManualRosterTable();
    })
    .catch(err => {
      console.log("Could not load students:", err);
    });
}

// =========================================================
// 9. UPLOAD PHOTO DETECTION
// =========================================================

function previewUploadImage() {
  const input = document.getElementById("photo-input");
  const resultDiv = document.getElementById("upload-result-container");
  const resultImg = document.getElementById("upload-result-img");
  const statusDiv = document.getElementById("upload-status");

  resultDiv.style.display = "none";
  statusDiv.style.display = "none";

  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = e => {
      resultImg.src = e.target.result;
    };
    reader.readAsDataURL(input.files[0]);
  }
}

function uploadAndDetect() {
  const input = document.getElementById("photo-input");
  const statusDiv = document.getElementById("upload-status");
  const resultDiv = document.getElementById("upload-result-container");
  const resultImg = document.getElementById("upload-result-img");
  const summaryDiv = document.getElementById("upload-summary");

  if (!input.files || !input.files[0]) {
    alert("Please select an image file first!");
    return;
  }

  statusDiv.textContent = `Processing image for ${activeSession.batch} in ${activeSession.room_no}...`;
  statusDiv.style.display = "block";

  const reader = new FileReader();
  reader.onload = e => {
    const base64Data = e.target.result;

    fetch("/api/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image: base64Data,
        batch: activeSession.batch,
        room_no: activeSession.room_no,
        class_time: activeSession.class_time
      })
    })
      .then(res => res.json())
      .then(data => {
        statusDiv.style.display = "none";
        if (data.error) {
          alert("Error: " + data.error);
          return;
        }

        resultImg.src = data.annotated_image;
        resultDiv.style.display = "block";

        const count = data.detections.length;
        if (count === 0) {
          summaryDiv.innerHTML = "<p>No faces detected in this image.</p>";
        } else {
          let names = data.detections.map(d => `${d.name} (${d.confidence}%)`).join(", ");
          summaryDiv.innerHTML = `<p>Found <strong>${count}</strong> face(s): ${names}<br><span style="color:#059669; font-weight:600;">Attendance logged for ${activeSession.batch} • ${activeSession.room_no} (${activeSession.class_time})</span></p>`;
        }
        loadAttendance();
        showToast(`Detected ${count} face(s) and logged attendance.`, "success");
      })
      .catch(err => {
        statusDiv.textContent = "Upload failed: " + err.message;
      });
  };
  reader.readAsDataURL(input.files[0]);
}

// =========================================================
// 10. ADMIN PANEL - ADD & DELETE STUDENTS
// =========================================================

function adminLoadStudentsTable() {
  if (!currentUser || currentUser.role !== "admin") return;

  fetch("/api/students")
    .then(res => res.json())
    .then(students => {
      const tbody = document.getElementById("admin-students-tbody");
      if (!tbody) return;

      if (!students || students.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#64748b;">No students registered in database.</td></tr>';
        return;
      }

      let html = "";
      students.forEach(s => {
        const faceBadge = s.has_face
          ? '<span class="badge badge-success">✓ Enrolled</span>'
          : '<span class="badge badge-neutral">No Photo</span>';

        html += `
          <tr>
            <td><strong>${s.student_id}</strong></td>
            <td>${s.name}</td>
            <td>${s.roll_no || "-"}</td>
            <td><span class="badge badge-neutral">${s.batch || "Batch A"}</span></td>
            <td>${faceBadge}</td>
            <td>
              <button class="btn btn-small btn-danger" onclick="adminDeleteStudent('${s.student_id}', '${escapeQuotes(s.name)}')">Delete Student</button>
            </td>
          </tr>
        `;
      });
      tbody.innerHTML = html;
    })
    .catch(err => console.log("Admin load students error:", err));
}

function escapeQuotes(str) {
  return (str || "").replace(/'/g, "\\'");
}

function previewNewStudentFile() {
  const input = document.getElementById("new-student-photo-file");
  const preview = document.getElementById("new-student-photo-preview");
  const wrapper = document.getElementById("enroll-preview-wrapper");

  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = e => {
      enrollingPhotoBase64 = e.target.result;
      preview.src = enrollingPhotoBase64;
      wrapper.style.display = "flex";
    };
    reader.readAsDataURL(input.files[0]);
  }
}

function snapFromWebcamForEnrollment() {
  const video = document.getElementById("webcam-video");
  const preview = document.getElementById("new-student-photo-preview");
  const wrapper = document.getElementById("enroll-preview-wrapper");

  if (isCameraRunning && video && video.videoWidth > 0) {
    const tempCanvas = document.createElement("canvas");
    tempCanvas.width = video.videoWidth;
    tempCanvas.height = video.videoHeight;
    const ctx = tempCanvas.getContext("2d");
    ctx.drawImage(video, 0, 0);

    enrollingPhotoBase64 = tempCanvas.toDataURL("image/jpeg", 0.9);
    preview.src = enrollingPhotoBase64;
    wrapper.style.display = "flex";
    showToast("Captured face photo from webcam.", "success");
  } else {
    navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
      .then(stream => {
        const tempVideo = document.createElement("video");
        tempVideo.srcObject = stream;
        tempVideo.play();
        tempVideo.onloadedmetadata = () => {
          setTimeout(() => {
            const tempCanvas = document.createElement("canvas");
            tempCanvas.width = tempVideo.videoWidth || 640;
            tempCanvas.height = tempVideo.videoHeight || 480;
            const ctx = tempCanvas.getContext("2d");
            ctx.drawImage(tempVideo, 0, 0);

            enrollingPhotoBase64 = tempCanvas.toDataURL("image/jpeg", 0.9);
            preview.src = enrollingPhotoBase64;
            wrapper.style.display = "flex";

            stream.getTracks().forEach(t => t.stop());
            showToast("Captured face photo from camera.", "success");
          }, 300);
        };
      })
      .catch(err => {
        alert("Could not access camera to capture snapshot: " + err.message);
      });
  }
}

function clearNewStudentPhoto() {
  enrollingPhotoBase64 = null;
  const fileInput = document.getElementById("new-student-photo-file");
  if (fileInput) fileInput.value = "";
  const wrapper = document.getElementById("enroll-preview-wrapper");
  if (wrapper) wrapper.style.display = "none";
}

function resetAddStudentForm() {
  document.getElementById("new-student-id").value = "";
  document.getElementById("new-student-name").value = "";
  document.getElementById("new-student-roll").value = "";
  document.getElementById("new-student-batch").value = "";
  clearNewStudentPhoto();
  const statusDiv = document.getElementById("admin-add-status");
  if (statusDiv) statusDiv.style.display = "none";
}

function adminSubmitAddStudent() {
  if (!currentUser || currentUser.role !== "admin") {
    alert("Unauthorized: Admin privileges required.");
    return;
  }

  const idInput = document.getElementById("new-student-id");
  const nameInput = document.getElementById("new-student-name");
  const rollInput = document.getElementById("new-student-roll");
  const batchInput = document.getElementById("new-student-batch");
  const statusDiv = document.getElementById("admin-add-status");
  const btn = document.getElementById("btn-add-student");

  const studentId = idInput.value.trim();
  const name = nameInput.value.trim();
  const roll = rollInput.value.trim();
  const batch = batchInput.value.trim() || "Batch A";

  if (!studentId || !name) {
    statusDiv.className = "error-msg";
    statusDiv.textContent = "Please fill in both Student ID and Full Name!";
    statusDiv.style.display = "block";
    return;
  }

  if (!/^[a-zA-Z0-9_\-]+$/.test(studentId)) {
    statusDiv.className = "error-msg";
    statusDiv.textContent = "Student ID can only contain letters, numbers, underscores, and hyphens (no spaces)!";
    statusDiv.style.display = "block";
    return;
  }

  btn.disabled = true;
  btn.textContent = "Processing & Training Face...";
  statusDiv.style.display = "none";

  fetch("/api/admin/students", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Role": currentUser.role
    },
    body: JSON.stringify({
      student_id: studentId,
      name: name,
      roll_no: roll,
      batch: batch,
      face_image: enrollingPhotoBase64
    })
  })
    .then(res => res.json().then(data => ({ status: res.status, body: data })))
    .then(({ status, body }) => {
      btn.disabled = false;
      btn.textContent = "Add & Enroll Student";

      if (status === 200 && body.success) {
        statusDiv.className = "success-msg";
        statusDiv.textContent = body.message;
        statusDiv.style.display = "block";
        showToast(`Student ${name} added!`, "success");

        resetAddStudentForm();
        adminLoadStudentsTable();
        loadStudents();
        loadBatches();
      } else {
        statusDiv.className = "error-msg";
        statusDiv.textContent = body.message || "Failed to add student.";
        statusDiv.style.display = "block";
      }
    })
    .catch(err => {
      btn.disabled = false;
      btn.textContent = "Add & Enroll Student";
      statusDiv.className = "error-msg";
      statusDiv.textContent = "Server error: " + err.message;
      statusDiv.style.display = "block";
    });
}

function adminDeleteStudent(studentId, studentName) {
  if (!currentUser || currentUser.role !== "admin") {
    alert("Unauthorized: Admin privileges required.");
    return;
  }

  const confirmMsg = `Are you sure you want to PERMANENTLY delete student:\n\n• Name: ${studentName}\n• ID: ${studentId}\n\nThis will remove them from the database and delete all enrolled face recognition data.`;
  if (!confirm(confirmMsg)) {
    return;
  }

  fetch(`/api/admin/students/${encodeURIComponent(studentId)}`, {
    method: "DELETE",
    headers: {
      "X-User-Role": currentUser.role
    }
  })
    .then(res => res.json().then(data => ({ status: res.status, body: data })))
    .then(({ status, body }) => {
      if (status === 200 && body.success) {
        showToast(body.message, "success");
        adminLoadStudentsTable();
        loadStudents();
        loadAttendance();
        loadBatches();
      } else {
        alert("Delete failed: " + (body.message || "Unknown error"));
      }
    })
    .catch(err => {
      alert("Error contacting server: " + err.message);
    });
}
