# Databricks Apps - Devloop Instructions

## Language Selection
- Default to using a node.js frontend and a pretty UI framework/components (e.g. React) when the demo is showcasing a "customer-facing" application (that is - the customer of your customer) or a really robust customer-internal application. Unless otherwise specified, do this!
- Use python frameworks for internal data applications or when explicitly told. DO NOT USE python when trying to make something beautiful and responsive.

## Code + Adding Resources
- Use the databricks-resource-deployment skill for guidance on configuration, deployment, and limitations.
- When your Databricks App is going to leverage a lakebase (database), databricks job, databricks secret, serving endpoint (models/llms), sql warehouse, or unity catalog object, ensure you update the resources in the app. For example, leveraging the databricks cli `databricks apps update` with a payload that includes the `resources` section here: https://docs.databricks.com/api/workspace/apps/createupdate. Some documentation in databricks-resource-deployment also mentions this.

## Development Process and Local Validation
*IMPORTANT* YOU MUST FOLLOW THIS PROCESS IN A LOOP UNTIL THE APP LOOKS AND WORKS AS EXPECTED *IMPORTANT*
1) Write the code LOCALLY
2) Run the app LOCALLY
3) Navigate to the app UI using the chrome devtools MCP, and inspect using the devtools MCP if necessary
4) Test that all of the features developed work in the UI and ensure that the app UI is beautiful
5) Run this workflow in a loop until you are satisfied with the results. If you are unable to run this workflow, stop and tell the user what to do in order to enable you to do this.

## Deployment and Remote Validation + Debugging
*IMPORTANT* YOU MUST FOLLOW THIS PROCESS IN A LOOP UNTIL THE REMOTELY DEPLOYED APP WORKS AS EXPECTED *IMPORTANT*
1) Deploy and run the code using the databricks CLI, including any additional necessary resources. Leverage the databricks-resource-deployment skill as a reference.
2) Navigate to the app UI using the chrome devtools MCP, and inspect using the devtools MCP if necessary
3) Test that all of the features developed work in the UI and ensure that the app UI is beautiful
4) The logs for the app are available at <app-url>/logz, if needed for debugging. If you need more info for debugging, go to <workspace-url>/apps/<app-name>
5) Run this workflow in a loop until you are satisfied with the results. If you are unable to run this workflow, stop and tell the user what to do in order to enable you to do this.

## Common Issues/Troubleshooting
1) If you see "App Not Available" "Sorry, the Databricks app you are trying to access is currently unavailable. Please try again later." This typically means that the app is deployed and started but NOT listening on the default port of 8000. So you must either configure the app to listen on this port by default, or set DATABRICKS_APP_PORT environment variable in your app.yaml to a different port, and deploy again.
