# 📂 EUDR GIS Auditor

<image src="./EudrGisAuditor.png"><image>

The **EUDR GIS Auditor** is a web-based tool designed to **validate, audit, and clean geospatial data**, specifically tailored to the requirements of the **European Union Deforestation Regulation (EUDR)**. It processes common GIS file formats, identifies and fixes errors, and provides an **interactive dashboard and map** for thorough review.

---

## 🛠️ Setup & Installation

The simplest way to run this application is with **Docker** and **Docker Compose**, which handle all dependencies automatically.

1. **Clone the repository:**

   ```bash
   git clone https://github.com/julio-collazos/EudrGisAuditor.git
   cd EudrGisAuditor
   ```

2. **Start the application (using Docker):**

   ```bash
   docker compose up --build
   ```
   Or using a Python environment

   ```bash
   conda create -n eudrgisauditor python=3.10
   conda activate eudrgisauditor
   pip install .
   ```

3. **Access the app:**
   Open your browser and navigate to 👉 [http://0.0.0.0:5000](http://0.0.0.0:5000)

---

## 🚀 Features

* **Geospatial Auditing** → Checks for geometry issues (e.g., self-intersections) and validates against standards like **WGS84**.
* **Automatic Fixes** → Corrects minor geometry errors to save you time.
* **Data Partitioning** → Classifies features as **valid**, **needs review**, or **conversion candidates** (e.g., small polygons → points).
* **Interactive Visualization** → Audit findings are displayed in a **dashboard** and on a **Leaflet-based map**, making flagged entities easy to inspect.

---

## ➡️ Roadmap / Next Steps

* 🔑 **User Authentication** → Add login system for managing sessions and data access.
* 📂 **Support Additional Formats** → Expand compatibility with more GIS formats.
* 🗄️ **Database Integration** → Store and manage audit results for long-term tracking.

---
