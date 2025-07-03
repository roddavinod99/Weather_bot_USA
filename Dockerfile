# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install any needed packages specified in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your font files
# The 'fonts/' directory from your GitHub repo will be copied into '/app/fonts/' in the container
COPY fonts/ /app/fonts/

# Copy the rest of your application code
# This will copy main.py into /app/
COPY . .

# Define the command to run your application when the container starts
# This will execute your main.py script
CMD ["python", "main.py"]