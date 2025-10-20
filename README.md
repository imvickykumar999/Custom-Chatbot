# Custom Chatbot

### How to Run `deploy.sh`

1.  **Save the file:** Save the content above as `deploy.sh` in your project root.
2.  **Make it executable:** Run `chmod +x deploy.sh` in your terminal.
3.  **Execute:** Run `./deploy.sh`

Once the deployment is complete, the script will output the local access URL. The application will be running at:

    http://localhost:8000

### How to Run `undeploy.sh`

1.  **Save the file:** Save the content above as `undeploy.sh` in your project root.
2.  **Make it executable:** Run `chmod +x undeploy.sh`.
3.  **Execute:** Run `./undeploy.sh`.

This script will reliably stop the background port-forward process and delete all the corresponding Kubernetes resources and the Minikube cluster.
