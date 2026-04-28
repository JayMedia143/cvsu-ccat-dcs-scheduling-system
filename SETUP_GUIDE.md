# 🚀 CvSU Scheduling System - Setup Guide (Tagalog/English)

Para ma-set up itong project sa ibang laptop, sundin lang ang mga steps sa ibaba.

---

## 📥 1. Essentials to Download (Bago mag-umpisa)

Siguraduhin na i-download at i-install muna ang mga ito:
1.  **Python 3.11.1**: [Download Python 3.11.1](https://www.python.org/downloads/release/python-3111/)
    - *Note: Siguraduhin na i-check ang box na **"Add Python to PATH"** habang nag-i-install.*
2.  **Git**: [Download Git for Windows](https://git-scm.com/download/win)
    - *Kailangan ito para sa pag-clone ng repository.*

---

## 🛠️ 2. Step-by-Step Installation (Windows Terminal/PowerShell)

Buksan ang terminal sa loob ng project folder at i-type ang mga sumusunod:

### 1. Gumawa ng Virtual Environment (venv)
Para hindi mag-conflict ang mga packages sa system mo.
```powershell
python -m venv venv
```

### 2. I-activate ang Virtual Environment
Dapat may makita kang `(venv)` sa unahan ng terminal mo pagkatapos nito.
```powershell
venv\Scripts\activate
```

### 3. I-install ang mga Requirements
Dito i-o-download lahat ng kailangang libraries (Flask, SQLAlchemy, etc.). Siguraduhin na may internet connection.
```powershell
pip install -r requirements.txt
```

### 4. Patakbuhin ang Application
Kapag tapos na ang installation, handa na ang app!
```powershell
python app.py
```

---

## ❓ Common Questions & Troubleshooting

### Paano kung iba ang Python Version ko?
Ang project na ito ay binuo gamit ang **Python 3.11.1**. Kung may iba kang versions at gusto mong piliin ang saktong version (halimbawa 3.11):
- Imbis na `python`, gamitin ang `py`:
  ```powershell
  py -3.11 -m venv venv
  ```

### Paano ko malalaman kung anong version ng Python ang gamit ko?
I-type ito sa terminal:
```powershell
python --version
```

### Hindi gumagana ang `venv\Scripts\activate`?
Kung may error tungkol sa "Execution Policy" sa PowerShell, i-type muna ito:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```
Tapos subukan ulit i-activate ang venv.

---

## 🤖 System Audit (Optional)
Kung gusto mong i-verify kung stable ang system sa laptop mo:
```powershell
python "System Testing/05_Functional_Testing/functional_robot.py"
```

**Enjoy Coding!** 🎓⚙️✨
