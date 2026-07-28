import { expect, test } from "@playwright/test";

const organizationId = "00000000-0000-0000-0000-000000000001";

type Execution = {
  id: string;
  work_item_id: string;
  status: string;
};

test("owner delivers an approved requirement through an isolated runner", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in with local OIDC" }).click();
  await page.getByLabel(/username or email/i).fill("owner@example.test");
  await page
    .getByRole("textbox", { name: "Password" })
    .fill("local-owner-only");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(
    page.getByRole("heading", { name: "Prepara tu equipo de entrega" }),
  ).toBeVisible();

  const githubStep = page
    .getByRole("heading", { name: "Conecta GitHub" })
    .locator("..");
  await githubStep.getByText("Opciones de desarrollo").click();
  await githubStep
    .getByRole("button", { name: "Conectar repositorio local simulado" })
    .click();

  const agentStep = page
    .getByRole("heading", {
      name: "Elige quién implementará los cambios",
    })
    .locator("..");
  await agentStep.getByText("Opciones de desarrollo").click();
  await agentStep
    .getByRole("button", { name: "Usar agente determinista sin red" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Ya puedes crear tu primer proyecto" }),
  ).toBeVisible({ timeout: 30_000 });
  await page.getByRole("link", { name: "Entrar al workspace" }).click();

  await expect(
    page.getByRole("heading", { name: "Delivery control plane" }),
  ).toBeVisible();
  await page.getByLabel("Project name").fill("Client Portal");
  await page
    .getByLabel("Description")
    .fill("Local vertical-slice project created through onboarding");
  await page.getByRole("button", { name: "Create project" }).click();

  const problem = `E2E requirement ${Date.now()}: publish verified status`;
  await page.getByLabel("Problem").fill(problem);
  await page.getByLabel("Intended users").fill("Release reviewers");
  await page
    .getByLabel(/Required functionality/)
    .fill("Update the delivery status\nRun independent verification");
  await page.getByLabel(/Exclusions/).fill("No production deployment");
  await page.getByLabel(/Constraints/).fill("Use the isolated local runner");

  const [intakeResponse] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes("/api/bff/control/organizations/") &&
        response.url().endsWith("/intakes") &&
        response.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Submit structured intake" }).click(),
  ]);
  expect(intakeResponse.ok()).toBeTruthy();

  const intake = page.locator("article").filter({ hasText: problem });
  await expect(intake).toBeVisible();
  await intake.getByRole("button", { name: "Draft specification v1" }).click();
  await expect(
    intake.getByRole("button", { name: /Submit v1 for approval/ }),
  ).toBeVisible();
  await intake.getByRole("button", { name: /Submit v1 for approval/ }).click();
  await expect(
    intake.getByRole("button", { name: "Approve exact version" }),
  ).toBeVisible();

  const [approvalResponse] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes("/specifications/") &&
        response.url().endsWith("/approve") &&
        response.request().method() === "POST",
    ),
    intake.getByRole("button", { name: "Approve exact version" }).click(),
  ]);
  expect(approvalResponse.ok()).toBeTruthy();
  const approval = (await approvalResponse.json()) as {
    work_item: { id: string };
  };
  const workItemId = approval.work_item.id;
  const workItem = page.getByTestId(`work-item-${workItemId}`);

  await expect(
    workItem.getByRole("button", { name: "Mark work item reviewed" }),
  ).toBeVisible();
  await workItem
    .getByRole("button", { name: "Mark work item reviewed" })
    .click();
  const readyButton = workItem.getByRole("button", {
    name: "Ready with $5.00 maximum",
  });
  await page.getByLabel("Repository for this work").selectOption({ index: 1 });
  await page.getByLabel("Coding agent").selectOption({ index: 1 });
  await page.getByLabel("Runner pool").selectOption({ index: 1 });
  await expect(readyButton).toBeEnabled();
  await readyButton.click();

  let executionId = "";
  await expect
    .poll(
      async () => {
        const response = await page.request.get(
          `/api/bff/delivery/organizations/${organizationId}/executions`,
        );
        expect(response.ok()).toBeTruthy();
        const executions = (await response.json()) as Execution[];
        const execution = executions.find(
          (candidate) => candidate.work_item_id === workItemId,
        );
        executionId = execution?.id ?? "";
        return execution?.status;
      },
      { timeout: 30_000 },
    )
    .toBe("AWAITING_APPROVAL");

  await page.reload();
  await page.getByLabel("Execution").selectOption(executionId);
  await page.getByRole("button", { name: "Approve execution budget" }).click();

  await expect
    .poll(
      async () => {
        const response = await page.request.get(
          `/api/bff/delivery/organizations/${organizationId}/executions`,
        );
        const executions = (await response.json()) as Execution[];
        return executions.find((candidate) => candidate.id === executionId)
          ?.status;
      },
      { timeout: 120_000 },
    )
    .toBe("DELIVERED");

  await page.reload();
  await page.getByLabel("Execution").selectOption(executionId);
  const timeline = page
    .getByRole("heading", { name: "Execution timeline" })
    .locator("..");
  await expect(timeline.getByText("DELIVERED", { exact: true })).toBeVisible();
  await expect(
    timeline.getByText(/independent verification passed/i),
  ).toBeVisible();
  await expect(timeline.getByText("Simulated pull request")).toBeVisible();
});
