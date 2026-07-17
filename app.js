const appState = {
    user: null,
    tasks: [],
    limit: 6,
    offset: 0,
    total: 0
};

document.addEventListener("DOMContentLoaded", () => {
    console.log("DOM LOADED");
    checkAuth();
    wireEventHandlers();
});

const loginView = document.getElementById("loginView");
const dashboardView = document.getElementById("dashboardView");
const loginError = document.getElementById("loginError");

function showLogin() {
    loginView.style.display = "block";
    dashboardView.style.display = "none";

    document.getElementById("usernameInput").value = "";
    document.getElementById("passwordInput").value = "";
    loginError.innerText = "";
}

function showDashboard() {

    loginView.style.display = "none";
    dashboardView.style.display = "block";

    const managerControls = document.getElementById("managerControls");

    // ✅ CRITICAL RESET
    managerControls.style.display = "none";

    if (appState.user.role === "manager") {
        managerControls.style.display = "block";
    }

    loadTasks();
}

async function checkAuth() {
    const response = await fetch("http://127.0.0.1:8000/users/me", {
        credentials: "include"
    });

    if (!response.ok) {
        showLogin();
        return;
    }

    const userData = await response.json();

    // ✅ STATE FIRST
    appState.user = userData;

    // ✅ UI AFTER STATE READY
    showDashboard();
}

function wireEventHandlers() {
    document.getElementById("loginBtn").onclick = login;
    document.getElementById("logoutBtn").onclick = logout;
    document.getElementById("createTaskBtn").onclick = createTask;
    document.getElementById("registerBtn").onclick = register;
    document.getElementById("prevBtn").onclick = prevPage;
    document.getElementById("nextBtn").onclick = nextPage;
    document.getElementById("sortDeadline").onclick = sortByDeadline;
    document.getElementById("sortStatus").onclick = sortByStatus;
}

async function register() {

    const errorBox = document.getElementById("registerError");
    errorBox.innerText = "";

    const username = document.getElementById("regUsername").value;
    const password = document.getElementById("regPassword").value;
    const role = document.getElementById("regRole").value;

    const response = await fetch("http://127.0.0.1:8000/register", {
        method: "POST",
        credentials: "include",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ username, password, role })
    });

    if (!response.ok) {
        errorBox.innerText = "Registration failed";
        return;
    }

    appState.offset = 0;

    checkAuth();
}

async function login() {

    loginError.innerText = "";

    const username = document.getElementById("usernameInput").value;
    const password = document.getElementById("passwordInput").value;

    const response = await fetch("http://127.0.0.1:8000/login", {
        method: "POST",
        credentials: "include",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ username, password })
    });

    if (!response.ok) {
        loginError.innerText = "Invalid credentials";
        return;
    }

    appState.offset = 0;
   
    checkAuth();
}

async function logout() {
    await fetch("http://127.0.0.1:8000/logout", {
        method: "POST",
        credentials: "include"
    });

    showLogin();
}


async function loadTasks() {

    const container = document.getElementById("taskContainer");

    container.innerHTML = "Loading tasks...";

    const response = await fetch(
        `http://127.0.0.1:8000/tasks/my?limit=${appState.limit}&offset=${appState.offset}`,
        { credentials: "include" }
    );

    if (!response.ok) {
        container.innerHTML = "Failed to load tasks";
        return;
    }

    const data = await response.json();

    appState.tasks = data.tasks;
    appState.total = data.total;

    renderTasks(data.tasks);
    updatePaginationControls();
}


function renderTasks(tasks) {

    const container = document.getElementById("taskContainer");

    // ✅ Guard 1 — Data validity
    if (!tasks || !Array.isArray(tasks)) {
        container.innerHTML = "Invalid task data";
        console.log("Invalid tasks:", tasks);
        return;
    }

    // ✅ Guard 2 — User state safety
    if (!appState.user) {
        container.innerHTML = "User not ready";
        console.log("User missing during render");
        return;
    }

    if (!tasks.length) {
        container.innerHTML = "No tasks";
        return;
    }

    container.innerHTML = "";

    tasks.forEach(task => {

        let actionButton = "";

        if (task.status === "created" && appState.user.role === "employee") {
            actionButton = `<button type="button" onclick="acceptTask(${task.id}, this)">Accept</button>`;
        }

        else if (task.status === "in_progress" && appState.user.role === "employee") {
            actionButton = `<button type="button" onclick="completeTask(${task.id}, this)">Complete</button>`;
        }

        else if (task.status === "completed" && appState.user.role === "manager") {
            actionButton = `<button type="button" onclick="reviewTask(${task.id}, this)">Review</button>`;
        }

        else if (task.status === "completed") {
            actionButton = `<p>Awaiting Review</p>`;
        }

        else if (task.status === "reviewed") {
            actionButton = `<p>Reviewed ✅</p>`;
        }

        if (appState.user.role === "manager") {
            actionButton += `<button type="button" onclick="deleteTask(${task.id}, this)">Delete</button>`;
        }

        const taskDiv = document.createElement("div");

        taskDiv.className = "task-card";   // ✅ CRITICAL ADDITION

        const now = new Date();
        const deadlineDate = new Date(task.deadline);

        let deadlineClass = "deadline-safe";
        let deadlineLabel = "On Track";

        if (deadlineDate < now && task.status !== "reviewed") {
            deadlineClass = "deadline-overdue";
            deadlineLabel = "Overdue";
        }
        else if ((deadlineDate - now) < (24 * 60 * 60 * 1000)) {
            deadlineClass = "deadline-urgent";
            deadlineLabel = "Due Soon";
        }

        taskDiv.innerHTML = `
            <div class="task-title">${task.title}</div>

            <div class="task-meta">${task.description}</div>

            <div class="task-meta">
                <b>Status:</b> 
                <span class="status status-${task.status}">
                    ${task.status}
                </span>
            </div>

            <div class="task-meta">
                <b>Deadline:</b> 
                <span class="${deadlineClass}">
                    ${deadlineDate.toLocaleString()} (${deadlineLabel})
                </span>
            </div>
            ${task.completed_at ? 
                `<div class="task-meta"><b>Completed At:</b> ${new Date(task.completed_at).toLocaleString()}</div>` 
                : ""}

            ${task.within_deadline !== null ? 
                `<div class="task-meta"><b>Within Deadline:</b> ${task.within_deadline ? "✅ Yes" : "❌ No"}</div>` 
                : ""}

            ${task.review ? 
                `<div class="task-meta"><b>Review:</b> ${task.review}</div>` 
                : ""}

            ${actionButton}
        `;
        
        console.log("Rendering task:", task.id);
        container.appendChild(taskDiv);
    });
}


async function acceptTask(taskId, button) {

    button.disabled = true;
    button.innerText = "Accepting...";

    const response = await fetch(`http://127.0.0.1:8000/tasks/accept/${taskId}`, {
        method: "POST",
        credentials: "include"
    });

    if (!response.ok) {
    const error = await response.json();

    button.disabled = false;
    button.innerText = "Accept";

    alert(error.detail || "Action failed");
    return;
    }

    loadTasks();
}


async function completeTask(taskId, button) {

    button.disabled = true;
    button.innerText = "Completing...";

    const response = await fetch(`http://127.0.0.1:8000/tasks/complete/${taskId}`, {
        method: "POST",
        credentials: "include"
    });

    if (!response.ok) {
    const error = await response.json();

    button.disabled = false;
    button.innerText = "Complete";

    alert(error.detail || "Action failed");
    return;
    }
    loadTasks();
}


async function createTask() {

    const title = document.getElementById("taskTitle").value;
    const description = document.getElementById("taskDescription").value;
    const assignedTo = parseInt(document.getElementById("taskAssignedTo").value);
    const deadline = document.getElementById("taskDeadline").value;

    const response = await fetch("http://127.0.0.1:8000/tasks/create", {
        method: "POST",
        credentials: "include",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            title,
            description,
            assigned_to: assignedTo,
            deadline
        })
    });

    if (!response.ok) {
        alert("Task creation failed");
        return;
    }

    loadTasks();   // Reload state
}


async function reviewTask(taskId, button) {

    const reviewText = prompt("Enter review:");

    if (!reviewText) return;

    button.disabled = true;
    button.innerText = "Reviewing...";

    const response = await fetch(
        `http://127.0.0.1:8000/tasks/review/${taskId}?review=${encodeURIComponent(reviewText)}`,
        {
            method: "POST",
            credentials: "include"
        }
    );

    if (!response.ok) {
    const error = await response.json();

    button.disabled = false;
    button.innerText = "Review";

    alert(error.detail || "Review failed");
    return;
    }

    loadTasks();
}


function prevPage() {
    if (appState.offset === 0) return;

    appState.offset -= appState.limit;
    loadTasks();
}


function nextPage() {
    if (appState.offset + appState.limit >= appState.total) return;

    appState.offset += appState.limit;
    loadTasks();
}


function updatePaginationControls() {

    const pageInfo = document.getElementById("pageInfo");

    const currentPage = Math.floor(appState.offset / appState.limit) + 1;
    const totalPages = Math.ceil(appState.total / appState.limit);

    pageInfo.innerText = `Page ${currentPage} / ${totalPages}`;
}


async function deleteTask(taskId, button) {

    if (!confirm("Delete this task?")) return;

    const response = await fetch(
        `http://127.0.0.1:8000/tasks/delete/${taskId}`,
        {
            method: "DELETE",
            credentials: "include"
        }
    );

    if (!response.ok) {
        const error = await response.json();
        alert(error.detail || "Delete failed");
        return;
    }

    loadTasks();
}


function sortByDeadline() {

    appState.tasks.sort((a, b) =>
        new Date(a.deadline) - new Date(b.deadline)
    );

    renderTasks(appState.tasks);
}


function sortByStatus() {

    const priority = {
        created: 1,
        in_progress: 2,
        completed: 3,
        reviewed: 4
    };

    appState.tasks.sort((a, b) =>
        priority[a.status] - priority[b.status]
    );

    renderTasks(appState.tasks);
}