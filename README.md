# Open Deep Research Docker + Kubernetes Setup

This project provides a containerized version of the [SmolagentsOpenDeepResearch](https://github.com/huggingface/smolagents) tool, deployed using Kubernetes and ArgoCD.

## Project Structure

- `Dockerfile` - Builds the container with the OpenDeepResearch tool
- `.github/workflows/docker-build-push.yml` - GitHub Actions workflow to build and push the image
- `k8s/` - Kubernetes deployment manifests
  - `deployment.yaml` - Deployment and Service definitions
  - `argocd-application.yaml` - ArgoCD Application manifest

## Setup Instructions

1. **GitHub Repository Setup**:
   - Push this code to your GitHub repository
   - Ensure GitHub Actions has permission to push to GitHub Container Registry

2. **Update Configuration**:
   - In `k8s/deployment.yaml`: Replace `USER_REPO` with your GitHub username/repo
   - In `k8s/argocd-application.yaml`: Replace `YOUR_USERNAME` with your GitHub username

3. **Deploy using ArgoCD**:
   ```bash
   kubectl apply -f k8s/argocd-application.yaml
   ```

## Usage

Once deployed, the Open Deep Research tool will run with the default query: "What topics are trending in AI research?"

To run with a different query:
1. Edit the `args` in `k8s/deployment.yaml`
2. Commit and push the changes
3. ArgoCD will automatically sync the changes

## Running Locally (Development)

Build the Docker image:
```bash
docker build -t open-deep-research .
```

Run the container with a custom query:
```bash
docker run open-deep-research "What is the current state of LLM research?"
```