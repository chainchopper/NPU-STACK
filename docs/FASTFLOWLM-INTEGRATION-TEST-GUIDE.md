# FastFlowLM Integration Test Guide

This document outlines comprehensive end-to-end testing of FastFlowLM integration across the NPU-STACK application.

## Test Environment

- **Frontend**: http://localhost:5173
- **Backend**: http://localhost:8010
- **Target**: Verify FastFlowLM surfacing in main user workflows
- **Hardware Detection**: AMD Ryzen AI NPU presence/absence

---

## Test Scenario 1: Dashboard Hardware Detection

### Objective
Verify that Dashboard displays FastFlowLM card with correct hardware detection state.

### Test Steps

1. **Navigate to Dashboard**
   - Go to http://localhost:5173/
   - Observe page load and hardware detection initialization

2. **Verify Dashboard Layout**
   - FastFlowLM card should render near the top of the page
   - Card should display: Title, 5 benefits list, quick start guide, dual CTAs
   - Card styling: 2px border with #667eea color, gradient background

3. **Test Conditional Display - AMD Ryzen AI NPU Detected**
   - If system has AMD Ryzen AI NPU:
     - ✅ Card should display: **"✅ Ryzen AI NPU is ready!"** (green alert)
     - Card should show: "5 benefits with emoji" (⚡ Power Efficient, 💻 No GPU Needed, etc.)
     - Two buttons should be visible:
       - Primary: "Open FastFlowLM" (blue, links to `/fastflowlm`)
       - Secondary: "Download FastFlowLM" (GitHub link)

4. **Test Conditional Display - Ryzen CPU Without NPU Driver**
   - If system has Ryzen CPU but NPU not detected:
     - ✅ Card should display: **"💡 Install NPU drivers"** (yellow alert)
     - Benefits list still visible
     - "Download" button should direct to FastFlowLM releases page

5. **Test Button Navigation**
   - Click "Open FastFlowLM" → should navigate to http://localhost:5173/fastflowlm
   - Click "Download FastFlowLM" → should open GitHub releases page

6. **Verify System Info Data Flow**
   - Open browser DevTools (F12) → Network tab
   - Refresh page and look for API call: `GET /api/benchmark/system-info`
   - Response should include fields:
     - `npu_available: true/false`
     - `amd_npu_available: true/false`
     - `processor: "AMD Ryzen AI 370"`
     - `flm_available: true/false`
     - `flm_version: "x.x.x"`

---

## Test Scenario 2: ChatPlayground Entry Point

### Objective
Verify FastFlowLM callout visibility in ChatPlayground (main chat interface).

### Test Steps

1. **Navigate to ChatPlayground**
   - Click "Chat Playground" or go to http://localhost:5173/chat
   - Wait for page to load

2. **Locate FastFlowLM Callout**
   - Scroll down to find **FastFlowLM section** with:
     - Zap icon ⚡
     - Label: "FASTFLOWLM · RYZEN AI NPU"
     - Tagline: "Inference on integrated NPU with 10x power efficiency"

3. **Verify Callout Styling**
   - Background: Gradient (#1a2035 to #141927)
   - Border: 2px solid #2d3748
   - Responsive layout (should stack on mobile)

4. **Test Callout Buttons**
   - **"Open FastFlowLM" button** → Click → Should navigate to `/fastflowlm`
   - **"Explain Setup" button** → Click → Should display help message with setup instructions

5. **Verify Message Content**
   - Help message should explain:
     - FastFlowLM purpose (NPU inference)
     - System requirement (AMD Ryzen AI)
     - Quick setup (download, run `flm serve`, use)

---

## Test Scenario 3: Orchestration Runtime Recommendations

### Objective
Verify Orchestration page displays runtime recommendations based on hardware.

### Test Steps

1. **Navigate to Orchestration**
   - Go to http://localhost:5173/orchestration
   - Wait for page to fully load (check for "Runtime Recommendations" section)

2. **Verify Recommendations Section**
   - Should appear after notice/error messages
   - Title: "Runtime Recommendations"
   - Cards displayed in responsive grid (max-width: 240px, auto-fit)

3. **Test FastFlowLM Recommendation Card (if AMD Ryzen AI NPU)**
   - Card should show:
     - Icon: ⚡
     - Title: "FastFlowLM (Ryzen AI NPU)"
     - Description: "Optimized for AMD Ryzen AI NPU. 10x power-efficient inference."
     - Link: "Open FastFlowLM →" (blue, #667eea)
   - Card styling: Light blue background (#667eea @ 10% opacity)
   - Clicking link should navigate to `/fastflowlm`

4. **Test CUDA Recommendation Card (if NVIDIA GPU present)**
   - Card should show:
     - Icon: 🎮
     - Title: "NVIDIA CUDA"
     - Device name and VRAM
   - Card styling: Cyan background

5. **Test ROCm Recommendation Card (if AMD GPU present)**
   - Card should show:
     - Icon: 🔴
     - Title: "AMD ROCm"
     - Version info
   - Card styling: Orange background

6. **Test FastFlowLM Status Card (if FastFlowLM installed)**
   - Card should show:
     - Icon: ✅
     - Title: "FastFlowLM Ready"
     - Version information
   - Card styling: Green background

---

## Test Scenario 4: FastFlowLM Page Direct Access

### Objective
Verify FastFlowLM page loads and communicates with backend correctly.

### Test Steps

1. **Navigate to FastFlowLM Page**
   - Go to http://localhost:5173/fastflowlm directly
   - Page should load without errors

2. **Verify Two Main Sections**
   - **Model Library Tab**: Browseable model catalog
   - **NPU Workspace Tab**: Server management and chat interface

3. **Test Server Status**
   - Check if FastFlowLM server is detected: Look for status badge
   - Backend call: `GET /api/flm/status`
   - Should return: `{available: true/false, version: "x.x.x"}`

4. **Test Model Operations (if server running)**
   - **Pull a model**: Button to pull from catalog
   - **Serve**: Button to start model on NPU
   - **Chat**: Interface to test inference

5. **Verify Activity Log**
   - Logs should show timestamped operations
   - Examples: "Model pulled", "Server started", "Chat completed"

---

## Test Scenario 5: Hardware Detection Data Flow

### Objective
Verify hardware detection information flows from backend through API to frontend state.

### Test Steps

1. **Backend Hardware Detection**
   - Command: `curl http://localhost:8010/api/benchmark/system-info`
   - Response should include complete hardware details:
     ```json
     {
       "processor": "AMD Ryzen AI 370",
       "cpu_count": 12,
       "memory_total_gb": 32,
       "npu_available": true,
       "amd_npu_available": true,
       "amd_npu_name": "AMD Neural Processing Unit",
       "flm_available": true,
       "flm_version": "0.x.x",
       "cuda_available": false,
       "rocm_available": false,
       ...
     }
     ```

2. **Frontend API Call**
   - DevTools → Network tab → Filter: "system-info"
   - Monitor `getSystemInfo()` call on page load
   - Response should match backend data

3. **State Propagation**
   - Dashboard receives sysInfo via props
   - FastFlowLMCard checks: `sysInfo.amd_npu_available` or `sysInfo.processor.includes('ryzen')`
   - Orchestration receives sysInfo and displays recommendations

---

## Test Scenario 6: End-to-End FastFlowLM Workflow

### Objective
Complete workflow from discovery to inference execution.

### Prerequisite
- FastFlowLM installed (`flm-setup.exe` run)
- System has AMD Ryzen AI NPU

### Test Steps

1. **User Discovery Phase**
   - Scenario: New user opens app
   - Expected: Dashboard shows FastFlowLM card (or ChatPlayground shows callout)
   - User recognizes FastFlowLM as primary NPU runtime

2. **Learning Phase**
   - User clicks "Explain Setup" button
   - Receives clear instructions:
     1. Download FastFlowLM
     2. Run `flm serve` to start server
     3. Open FastFlowLM tab
     4. Test model inference

3. **Setup Phase**
   - User downloads FastFlowLM from GitHub link
   - Installs via `flm-setup.exe`
   - Runs: `flm serve` (starts on port 52625)

4. **Access Phase**
   - User clicks "Open FastFlowLM" button
   - FastFlowLM page loads at `/fastflowlm`
   - Page detects running server: Shows ✅ "FastFlowLM Ready"

5. **Model Selection Phase**
   - User browses Model Library tab
   - Selects a model (e.g., `TinyLlama`, `Llama2-7B`)
   - Clicks "Pull Model"

6. **Inference Phase**
   - User navigates to NPU Workspace tab
   - Clicks "Serve Model"
   - Backend executes: `flm serve --model <selected_model>`
   - User enters prompt in Chat interface
   - Inference executes on NPU

7. **Verification**
   - Response displays in chat
   - Activity log shows timestamps
   - No errors in browser console (F12 → Console tab)

---

## Acceptance Criteria

### ✅ All Tests Pass When:

1. **Dashboard**
   - [ ] FastFlowLM card renders
   - [ ] Hardware detection logic displays correct state
   - [ ] Buttons navigate to correct URLs
   - [ ] Conditional alerts show based on hardware

2. **ChatPlayground**
   - [ ] FastFlowLM callout is visible
   - [ ] Buttons are functional and navigate correctly
   - [ ] Help message explains FastFlowLM purpose

3. **Orchestration**
   - [ ] Runtime Recommendations section displays
   - [ ] FastFlowLM card shows for Ryzen AI systems
   - [ ] All recommendation cards render with correct styling
   - [ ] Links are functional

4. **FastFlowLM Page**
   - [ ] Page loads without errors
   - [ ] Server status is detected
   - [ ] Model operations (pull/serve/chat) are available
   - [ ] Activity log records actions

5. **Data Flow**
   - [ ] `GET /api/benchmark/system-info` returns complete hardware data
   - [ ] Frontend receives and displays data correctly
   - [ ] All conditional logic works as expected

6. **End-to-End Workflow**
   - [ ] User can discover FastFlowLM from main pages
   - [ ] User receives setup instructions
   - [ ] User can complete full inference workflow
   - [ ] No console errors or broken navigation

---

## Troubleshooting

### Issue: FastFlowLM card doesn't render on Dashboard
- **Check**: Browser console for errors (F12 → Console)
- **Check**: API response: `curl http://localhost:8010/api/benchmark/system-info`
- **Fix**: Restart backend: `python backend/main.py`

### Issue: Hardware detection shows false for Ryzen AI
- **Check**: Windows Device Manager → System devices for "AMD IPU" or "Neural Processing Unit"
- **Check**: PowerShell: `Get-WmiObject Win32_PnPDevice | Where-Object {$_.Name -like '*NPU*'}`
- **Fix**: Install AMD Ryzen AI drivers from official AMD website

### Issue: "Open FastFlowLM" button doesn't navigate
- **Check**: Frontend routing in App.jsx has route `/fastflowlm`
- **Check**: Browser console for routing errors
- **Fix**: Ensure FastFlowLM.jsx component is exported and route is registered

### Issue: Runtime Recommendations section missing from Orchestration
- **Check**: Frontend compilation errors (npm run build or dev server logs)
- **Check**: getSystemInfo is imported and called in loadAll()
- **Fix**: Restart frontend dev server: `npm run dev`

---

## Performance Notes

- Hardware detection runs once on app load (~200-500ms)
- FastFlowLM status check is non-blocking (uses `.catch(() => null)`)
- Recommendations render in ~50-100ms
- No performance impact to main app workflow

---

## Success Indicators

✨ **Integration is successful when:**

1. Users landing on Dashboard/ChatPlayground immediately see FastFlowLM option
2. Ryzen AI users get specific "NPU Ready" messaging
3. Users without NPU get helpful "Install drivers" messaging  
4. Orchestration page provides one-click access to appropriate runtimes
5. Complete workflow from discovery → setup → inference is smooth and guided
6. Zero console errors or broken navigation paths

