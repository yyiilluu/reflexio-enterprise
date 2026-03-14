# built using python:3.10
FROM python:3.10

# built using BaseDockerfile, using linux amd64
# FROM reflexio-amd64:latest

# built using BaseDockerfile
# FROM reflexio-mac

WORKDIR ./

# Copy the rest of the application
COPY . .

# Install dependencies
RUN pip install -r docker/requirements.txt

# Install Supabase CLI
RUN curl -fsSL https://supabase.com/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

EXPOSE 8080
EXPOSE 8081

CMD ["/bin/bash", "./run_services.sh"]
