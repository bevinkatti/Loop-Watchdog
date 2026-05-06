const guidedTrialButton = document.getElementById("guided-trial-button");
const feedback = document.getElementById("trial-feedback");

if (guidedTrialButton && feedback) {
  guidedTrialButton.addEventListener("click", async () => {
    guidedTrialButton.disabled = true;
    feedback.textContent = "Creating a guided trial session...";
    try {
      const response = await fetch("/v1/watchdog/demo/guided-trial", {
        method: "POST",
        headers: { accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Guided trial failed with status ${response.status}`);
      }
      const payload = await response.json();
      feedback.textContent = "Guided trial ready. Opening the dashboard...";
      window.setTimeout(() => {
        window.location.href = `/dashboard?session=${encodeURIComponent(payload.session_id)}`;
      }, 700);
    } catch (error) {
      feedback.textContent =
        error instanceof Error ? error.message : "Failed to create guided trial.";
      guidedTrialButton.disabled = false;
    }
  });
}
