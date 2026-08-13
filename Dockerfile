FROM frappe/erpnext:v15

USER frappe
WORKDIR /home/frappe/frappe-bench

# Copy the momentum app source into the bench apps directory
COPY --chown=frappe:frappe . apps/momentum

# Register momentum with the bench's Python path using the same .pth mechanism
# that frappe and erpnext use (see env/lib/python3.11/site-packages/frappe.pth)
RUN echo "/home/frappe/frappe-bench/apps/momentum" \
    > /home/frappe/frappe-bench/env/lib/python3.11/site-packages/momentum.pth
