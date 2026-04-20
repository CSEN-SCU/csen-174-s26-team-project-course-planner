const steps = [...document.querySelectorAll(".step")];
const stepLabel = document.getElementById("stepLabel");
const progressFill = document.getElementById("progressFill");
const backBtn = document.getElementById("backBtn");
const nextBtn = document.getElementById("nextBtn");
const submitBtn = document.getElementById("submitBtn");
const form = document.getElementById("wizardForm");
const resultsSection = document.getElementById("results");
const advisorTip = document.getElementById("advisorTip");
const plansContainer = document.getElementById("plansContainer");

let currentStep = 1;

function syncWizardUI() {
  steps.forEach((step) => {
    step.classList.toggle("active", Number(step.dataset.step) === currentStep);
  });

  stepLabel.textContent = `Step ${currentStep} of ${steps.length}`;
  progressFill.style.width = `${(currentStep / steps.length) * 100}%`;

  backBtn.disabled = currentStep === 1;
  nextBtn.classList.toggle("hidden", currentStep === steps.length);
  submitBtn.classList.toggle("hidden", currentStep !== steps.length);
}

function currentStepField() {
  const active = document.querySelector(`.step[data-step="${currentStep}"] textarea`);
  return active;
}

function validateCurrentStep() {
  const field = currentStepField();
  if (!field.value.trim()) {
    field.reportValidity();
    return false;
  }
  return true;
}

backBtn.addEventListener("click", () => {
  currentStep = Math.max(1, currentStep - 1);
  syncWizardUI();
});

nextBtn.addEventListener("click", () => {
  if (!validateCurrentStep()) return;
  currentStep = Math.min(steps.length, currentStep + 1);
  syncWizardUI();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!validateCurrentStep()) return;

  submitBtn.disabled = true;
  submitBtn.textContent = "Generating...";
  plansContainer.innerHTML = "";
  resultsSection.classList.remove("hidden");
  advisorTip.textContent = "";

  const payload = {
    persona: document.getElementById("persona").value.trim(),
    transcript: document.getElementById("transcript").value.trim(),
    goals: document.getElementById("goals").value.trim(),
    constraints: document.getElementById("constraints").value.trim(),
    priorities: document.getElementById("priorities").value.trim(),
  };

  try {
    const response = await fetch("/api/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed.");

    advisorTip.textContent = data.advisorTip || "";
    renderPlans(data.plans || []);
  } catch (error) {
    plansContainer.innerHTML = `<p class="error">${error.message}</p>`;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Generate Plans";
  }
});

function renderPlans(plans) {
  if (!plans.length) {
    plansContainer.innerHTML = `<p class="error">No plans returned. Please try again.</p>`;
    return;
  }

  plansContainer.innerHTML = plans
    .map((plan) => {
      const courses = (plan.courses || [])
        .map(
          (course) =>
            `<li><strong>${course.code} - ${course.title}</strong><br/>${course.reason}</li>`,
        )
        .join("");

      return `
        <article class="plan">
          <h3>${plan.name}</h3>
          <p>${plan.whyThisWorks}</p>
          <p class="plan-meta"><strong>Estimated workload:</strong> ${plan.estimatedWorkload}</p>
          <p class="plan-meta"><strong>Quality vs difficulty note:</strong> ${plan.qualityVsDifficultyNote}</p>
          <ul>${courses}</ul>
        </article>
      `;
    })
    .join("");
}

async function refreshApiStatus() {
  const el = document.getElementById("apiStatus");
  if (!el) return;
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    if (data.geminiConfigured) {
      el.textContent =
        "Live AI: server loaded GEMINI_API_KEY from prototypes/Jason/.env (restart after you change it).";
      el.className = "api-status ok";
    } else {
      el.textContent =
        "Demo mode: no API key loaded. Put GEMINI_API_KEY in prototypes/Jason/.env next to server.js, save, then run npm start again.";
      el.className = "api-status warn";
    }
  } catch {
    el.textContent = "Could not reach the API. Is the server running?";
    el.className = "api-status err";
  }
}

syncWizardUI();
refreshApiStatus();
