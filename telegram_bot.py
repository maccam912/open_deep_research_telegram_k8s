import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from kubernetes import client, config
import yaml
import uuid
import time
from datetime import datetime

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load Kubernetes configuration
try:
    config.load_incluster_config()  # Load in-cluster config if running inside K8s
except config.ConfigException:
    config.load_kube_config()  # Load config from ~/.kube/config if running locally

k8s_batch_api = client.BatchV1Api()
k8s_core_api = client.CoreV1Api()

# Define the namespace to use for all Kubernetes operations
K8S_NAMESPACE = "opendeepresearch"

# Dictionary to keep track of jobs and their corresponding chat_ids
active_jobs = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "Hi! I'm your research assistant. Ask me anything, and I'll process it for you."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Just send me your research question, and I'll process it using the deep research system."
    )

def create_job(query: str, chat_id: int) -> str:
    """Create a Kubernetes job for the given query."""
    job_name = f"research-job-{uuid.uuid4().hex[:10]}"
    
    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "labels": {
                "app": "open-deep-research",
                "chat-id": str(chat_id)
            }
        },
        "spec": {
            "ttlSecondsAfterFinished": 300,  # Delete job 5 minutes after completion
            "template": {
                "metadata": {
                    "labels": {
                        "app": "open-deep-research",
                        "chat-id": str(chat_id)
                    }
                },
                "spec": {
                    "containers": [
                        {
                            "name": "open-deep-research",
                            "image": "ghcr.io/maccam912/open_deep_research_telegram_k8s/open-deep-research:latest",
                            # "image": "ghcr.io/maccam912/browser-use-agent:latest",
                            "args": [query],
                            "env": [
                                {
                                    "name": "MODEL_ID",
                                    "value": os.getenv("MODEL_ID", "qwen/qwq-32b:free")
                                },
                                {
                                    "name": "HF_TOKEN",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "research-api-secrets",
                                            "key": "hf-token"
                                        }
                                    }
                                },
                                {
                                    "name": "OPENROUTER_API_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "research-api-secrets",
                                            "key": "openrouter-api-key"
                                        }
                                    }
                                }
                            ],
                            "resources": {
                                "limits": {
                                    "cpu": "1",
                                    "memory": "2Gi"
                                },
                                "requests": {
                                    "cpu": "500m",
                                    "memory": "1Gi"
                                }
                            }
                        }
                    ],
                    "restartPolicy": "Never"
                }
            },
            "backoffLimit": 1
        }
    }
    
    # Create the job in Kubernetes
    k8s_batch_api.create_namespaced_job(
        body=job,
        namespace=K8S_NAMESPACE
    )
    
    logger.info(f"Created job {job_name} for chat_id {chat_id}")
    return job_name

async def check_job_status():
    """Check the status of all active jobs and respond with results if completed."""
    jobs_to_remove = []
    
    for job_name, job_info in active_jobs.items():
        try:
            job = k8s_batch_api.read_namespaced_job(job_name, K8S_NAMESPACE)
            
            if job.status.succeeded:
                # Job completed successfully
                chat_id = job_info["chat_id"]
                
                # Get pod associated with this job
                pod_label_selector = f"job-name={job_name}"
                pods = k8s_core_api.list_namespaced_pod(
                    namespace=K8S_NAMESPACE, 
                    label_selector=pod_label_selector
                )
                
                if pods.items:
                    pod_name = pods.items[0].metadata.name
                    
                    # Get logs from the pod
                    logs = k8s_core_api.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=K8S_NAMESPACE
                    )
                    
                    # Extract the answer from logs
                    answer = logs.strip()
                    if "Got this answer:" in answer:
                        answer = answer.split("Got this answer:", 1)[1].strip()
                    
                    # Delete the processing message
                    if "processing_message_id" in job_info:
                        try:
                            await job_info["bot"].delete_message(
                                chat_id=chat_id,
                                message_id=job_info["processing_message_id"]
                            )
                        except Exception as e:
                            logger.error(f"Error deleting processing message: {e}")
                    
                    # Send the result back to the user
                    await job_info["bot"].send_message(
                        chat_id=chat_id, 
                        text=f"Research result: {answer}"
                    )
                else:
                    # Delete the processing message
                    if "processing_message_id" in job_info:
                        try:
                            await job_info["bot"].delete_message(
                                chat_id=chat_id,
                                message_id=job_info["processing_message_id"]
                            )
                        except Exception as e:
                            logger.error(f"Error deleting processing message: {e}")
                            
                    await job_info["bot"].send_message(
                        chat_id=chat_id, 
                        text="Could not retrieve research results. Please try again."
                    )
                
                jobs_to_remove.append(job_name)
            
            elif job.status.failed:
                # Job failed
                chat_id = job_info["chat_id"]
                
                # Delete the processing message
                if "processing_message_id" in job_info:
                    try:
                        await job_info["bot"].delete_message(
                            chat_id=chat_id,
                            message_id=job_info["processing_message_id"]
                        )
                    except Exception as e:
                        logger.error(f"Error deleting processing message: {e}")
                
                await job_info["bot"].send_message(
                    chat_id=chat_id, 
                    text="Sorry, the research job failed. Please try again later."
                )
                jobs_to_remove.append(job_name)
        
        except Exception as e:
            logger.error(f"Error checking job {job_name}: {e}")
    
    # Remove processed jobs from tracking
    for job_name in jobs_to_remove:
        del active_jobs[job_name]

async def job_monitor(context: ContextTypes.DEFAULT_TYPE):
    """Background task that periodically checks job status."""
    await check_job_status()

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process the user message and create a job."""
    query = update.message.text
    chat_id = update.effective_chat.id
    
    # Let the user know we're processing
    processing_message = await update.message.reply_text("Processing your research query... This may take a few minutes.")
    
    try:
        # Create a Kubernetes job
        job_name = create_job(query + "\nAlways cite sources used to answer the question with links to sources.", chat_id)
        
        # Add job to tracking
        active_jobs[job_name] = {
            "chat_id": chat_id,
            "query": query,
            "timestamp": datetime.now(),
            "bot": context.bot,
            "processing_message_id": processing_message.message_id
        }
        
        logger.info(f"Added job {job_name} to tracking for chat_id {chat_id}")
        
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")
        logger.error(f"Error creating job: {e}")

def main() -> None:
    """Start the bot."""
    # Get the Telegram token from environment variable
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set")
        return
    
    # Create the Application
    application = Application.builder().token(telegram_token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    
    # Add job to periodically check K8s job status
    application.job_queue.run_repeating(job_monitor, interval=10, first=10)
    
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()