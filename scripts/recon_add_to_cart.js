/**
 * GoingToCamp "Add to Stay" Network Recon Script
 *
 * This script opens washington.goingtocamp.com in a browser, intercepts all
 * network requests, and logs the exact API call made when you click "Add to Stay".
 *
 * Usage:
 *   npx playwright test scripts/recon_add_to_cart.js --headed
 *   OR
 *   node scripts/recon_add_to_cart.js
 *
 * Steps:
 *   1. Browser opens to the WA State Parks booking search page
 *   2. You search for a campground and select a campsite
 *   3. When you click "Add to Stay", the script captures the API call
 *   4. Results are saved to scripts/recon_output.json
 */

const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE_URL = "https://washington.goingtocamp.com";
const OUTPUT_FILE = path.join(__dirname, "recon_output.json");

// Collect all intercepted requests
const capturedRequests = [];

async function main() {
  const browser = await chromium.launch({
    headless: false,
    slowMo: 100,
  });

  const context = await browser.newContext({
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  });

  const page = await context.newPage();

  // Intercept all requests
  page.on("request", (request) => {
    const url = request.url();
    const method = request.method();

    // Only capture API calls (POST/PUT/PATCH) or anything to /api/
    if (
      method !== "GET" ||
      url.includes("/api/") ||
      url.includes("cart") ||
      url.includes("booking") ||
      url.includes("reservation")
    ) {
      const entry = {
        timestamp: new Date().toISOString(),
        method: method,
        url: url,
        headers: request.headers(),
        postData: request.postData() || null,
      };
      capturedRequests.push(entry);

      // Highlight non-GET requests (likely the cart mutation)
      if (method !== "GET") {
        console.log("\n" + "=".repeat(80));
        console.log(`>>> ${method} ${url}`);
        console.log(`    Headers: ${JSON.stringify(request.headers(), null, 2)}`);
        if (request.postData()) {
          console.log(`    Body: ${request.postData()}`);
        }
        console.log("=".repeat(80) + "\n");
      }
    }
  });

  // Also capture responses for non-GET requests
  page.on("response", async (response) => {
    const request = response.request();
    if (request.method() !== "GET") {
      try {
        const body = await response.text();
        console.log(`<<< ${response.status()} ${request.method()} ${request.url()}`);
        console.log(`    Response: ${body.substring(0, 500)}`);

        // Add response to the matching captured request
        const matchIdx = capturedRequests.findIndex(
          (r) => r.url === request.url() && r.method === request.method() && !r.response
        );
        if (matchIdx !== -1) {
          capturedRequests[matchIdx].response = {
            status: response.status(),
            headers: response.headers(),
            body: body.substring(0, 2000),
          };
        }
      } catch (e) {
        // Response body may not be available
      }
    }
  });

  console.log("=".repeat(80));
  console.log("GoingToCamp Add-to-Cart Network Recon");
  console.log("=".repeat(80));
  console.log("");
  console.log("Instructions:");
  console.log("  1. The browser will open to washington.goingtocamp.com");
  console.log("  2. Search for a campground (e.g., Deception Pass)");
  console.log("  3. Select dates and find an available campsite");
  console.log("  4. Click 'Add to Stay' — the script will capture the API call");
  console.log("  5. Close the browser when done (or press Ctrl+C)");
  console.log("");
  console.log(`Output will be saved to: ${OUTPUT_FILE}`);
  console.log("=".repeat(80));
  console.log("");

  // Navigate to the site
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  console.log("Page loaded. Follow the instructions above...\n");

  // Wait for the user to interact and close the browser
  // The script stays alive until the browser is closed
  await page.waitForEvent("close", { timeout: 600000 }).catch(() => {});

  // Save results
  if (capturedRequests.length > 0) {
    // Filter to most interesting requests (non-GET, or cart/booking related)
    const interesting = capturedRequests.filter(
      (r) =>
        r.method !== "GET" ||
        r.url.includes("cart") ||
        r.url.includes("book") ||
        r.url.includes("reservation") ||
        r.url.includes("stay")
    );

    const output = {
      totalCaptured: capturedRequests.length,
      interestingRequests: interesting,
      allRequests: capturedRequests,
    };

    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2));
    console.log(`\nSaved ${capturedRequests.length} requests to ${OUTPUT_FILE}`);
    console.log(`  Interesting (non-GET / cart-related): ${interesting.length}`);
  } else {
    console.log("\nNo API requests captured.");
  }

  await browser.close();
}

main().catch((err) => {
  console.error("Error:", err);
  process.exit(1);
});
