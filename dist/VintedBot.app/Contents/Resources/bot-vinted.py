import tkinter as tk
from tkinter import ttk
import threading
import time
import random 
import re
import webbrowser
from urllib.parse import quote_plus

# --- NOUVEAUX IMPORTS POUR L'AFFICHAGE DES IMAGES ---
import requests
from io import BytesIO
# Nécessite : pip install Pillow
from PIL import Image, ImageTk 
# ----------------------------------------------------

# --- Modules pour le Bot (Automating) ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By 
from selenium.common.exceptions import NoSuchElementException
# ----------------------------------------

# URL DE BASE AVEC LES FILTRES 
URL_BASE_FILTREE = "https://www.vinted.be/catalog?catalog[]=5&price_from=10&currency=EUR&price_to=30" 

# --- CONFIGURATION DU BOT ET DU TIMING ---
SELECTEUR_ARTICLE = "div.feed-grid__item-content" 
SELECTEUR_IMAGE_ALT = "img.web_ui__Image__content"          
SELECTEUR_PRIX = "p[data-testid*='--price-text']" 
SELECTEUR_LIEN = "a[data-testid*='overlay-link']"

DELAI_RAFRAICHISSEMENT = 30 
TAILLE_BATCH = 10 
DELAI_BATCH_PROCESSING = 10 


# --- COULEURS ET STYLES MODERNES ---
BACKGROUND_COLOR = '#FFFFFF'
PRIMARY_COLOR = '#333333'
ACCENT_COLOR_ACTION = '#E74C3C'
ACCENT_COLOR_ALERTE = '#1ABC9C' 
LINK_COLOR = '#3498DB' 
PLACEHOLDER_COLOR = '#95A5A6' # Couleur pour le texte de statut dans l'interface

# -------------------------------------------------------------------
# CLASSE UTILITAIRE : ScrollableFrame (Nécessaire pour afficher les images)
# -------------------------------------------------------------------
class ScrollableFrame(ttk.Frame):
    """Crée un conteneur avec une barre de défilement verticale."""
    def __init__(self, container):
        super().__init__(container)
        canvas = tk.Canvas(self, borderwidth=0, background=BACKGROUND_COLOR)
        self.interior = ttk.Frame(canvas, padding=5, style='TFrame')
        vbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        
        canvas.configure(yscrollcommand=vbar.set)
        
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.create_window((0, 0), window=self.interior, anchor="nw", tags="self.interior")
        
        self.interior.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self.interior.bind_all('<MouseWheel>', self._on_mousewheel) # Pour le défilement Windows/Mac
        
        # Stocker la référence de l'objet Canvas pour la mise à jour
        self.canvas = canvas 

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def update_scroll_region(self):
        # Nécessaire pour forcer Tkinter à recalculer la zone de défilement après l'ajout d'images.
        self.canvas.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

# -------------------------------------------------------------------
# CLASSE PRINCIPALE : VintedBotGUI
# -------------------------------------------------------------------
class VintedBotGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vinted Sniper | Photos Directes (V16)")
        self.geometry("750x650") 
        self.resizable(True, True) 
        
        self.is_running = False
        self.bot_thread = None
        self.articles_deja_vus = set()
        self.driver = None 
        self.service = None 
        self.photo_refs = [] # ⭐ TRÈS IMPORTANT : Stocker les références des images pour éviter le garbage collector

        self.create_widgets()
        
    def create_widgets(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        
        self.configure(bg=BACKGROUND_COLOR)
        style.configure('TFrame', background=BACKGROUND_COLOR)
        style.configure('TLabel', background=BACKGROUND_COLOR, foreground=PRIMARY_COLOR, font=('Arial', 11))
        
        # Styles de boutons
        style.configure('Accent.TButton', background=ACCENT_COLOR_ACTION, foreground='white', borderwidth=0, relief='flat', font=('Arial', 11, 'bold'))
        style.map('Accent.TButton', background=[('active', '#C0392B')])
        style.configure('TButton', background='#BDC3C7', foreground=PRIMARY_COLOR, borderwidth=0, relief='flat', font=('Arial', 11, 'bold'))
        style.map('TButton', background=[('active', '#95A5A6')])

        # Nouveau style pour les conteneurs d'articles (fond légèrement différent pour la séparation)
        style.configure('Article.TFrame', background='#F0F0F0') 

        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill='both', expand=True)

        # --- Section Contrôles ---
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill='x', pady=10)
        
        ttk.Label(control_frame, text="Marque à chercher :", font=('Arial', 11, 'bold')).pack(side='left', padx=5)
        self.marque_entry = ttk.Entry(control_frame, width=25)
        self.marque_entry.pack(side='left', padx=15)
        self.marque_entry.insert(0, "Stüssy") # Marque par défaut modifiée pour plus de chance de trouver des résultats

        # --- Boutons et Statut (Alignés) ---
        button_status_frame = ttk.Frame(main_frame)
        button_status_frame.pack(fill='x', pady=15)
        
        self.start_button = ttk.Button(button_status_frame, text="▶ DÉMARRER", command=self.start_bot, style='Accent.TButton')
        self.start_button.pack(side='left', padx=10, pady=5)
        
        self.stop_button = ttk.Button(button_status_frame, text="■ ARRÊTER", command=self.stop_bot, state=tk.DISABLED)
        self.stop_button.pack(side='left', padx=10, pady=5)

        self.status_label = ttk.Label(button_status_frame, text="Prêt", font=('Arial', 11, 'bold'))
        self.status_label.pack(side='right', padx=10, pady=5)
        
        # --- Section Log (ScrollableFrame) ---
        log_label = ttk.Label(main_frame, text="Nouveaux Articles Trouvés :", font=('Arial', 11, 'bold')).pack(anchor='w', pady=(10, 0))
        log_frame = ttk.Frame(main_frame)
        log_frame.pack(fill='both', expand=True, pady=(5, 0))
        
        # ⭐ NOUVEAU : Utilisation de ScrollableFrame
        self.log_scrollable_frame = ScrollableFrame(log_frame)
        self.log_scrollable_frame.pack(fill='both', expand=True)

    def log_message(self, message, tag=None):
        """Affiche les messages de statut (utilise le journal en bas du ScrollableFrame pour la simplicité)"""
        # Étant donné que nous n'avons plus de 'scrolledtext', nous allons afficher les messages de statut
        # directement dans la zone de défilement pour conserver la simplicité du code
        status_label = ttk.Label(self.log_scrollable_frame.interior, text=message, foreground=PLACEHOLDER_COLOR, font=('Consolas', 9))
        status_label.pack(anchor='w', padx=10, pady=1)
        self.log_scrollable_frame.update_scroll_region()
        self.log_scrollable_frame.canvas.yview_moveto(1.0) # Défiler jusqu'à la fin


    def display_article(self, item):
        """Affiche un article avec sa photo et ses détails dans le ScrollableFrame."""
        
        # Création du conteneur pour l'article (fond légèrement gris)
        article_frame = ttk.Frame(self.log_scrollable_frame.interior, padding=5, style='Article.TFrame')
        article_frame.pack(fill='x', pady=5, padx=5, anchor='n')
        
        # 1. Téléchargement et Affichage de l'Image
        self.download_and_display_image(article_frame, item['photo_url'])
        
        # 2. Affichage des Détails du Texte (côté droit de l'image)
        text_frame = ttk.Frame(article_frame, padding=(10, 0), style='Article.TFrame')
        text_frame.pack(side='left', fill='y')
        
        # Titre (Alerte)
        ttk.Label(text_frame, text=f"✨ {item['titre']}", background='#F0F0F0', foreground=ACCENT_COLOR_ALERTE, font=('Arial', 11, 'bold')).pack(anchor='w', pady=(0, 2))
        # Prix
        ttk.Label(text_frame, text=f"💰 Prix : {item['prix']}", background='#F0F0F0', foreground=PRIMARY_COLOR, font=('Arial', 11)).pack(anchor='w', pady=2)
        
        # Lien Vinted
        link_text = "🔗 Voir l'article complet"
        link_label = ttk.Label(text_frame, text=link_text, background='#F0F0F0', foreground=LINK_COLOR, cursor="hand2", font=('Arial', 10, 'underline'))
        link_label.pack(anchor='w', pady=(5, 0))
        link_label.bind('<Button-1>', lambda e: self.open_link(item['lien']))
        
        # Mettre à jour la zone de défilement
        self.log_scrollable_frame.update_scroll_region()
        self.log_scrollable_frame.canvas.yview_moveto(1.0) # Défiler jusqu'à la fin


    def download_and_display_image(self, container, url):
        """Télécharge l'image depuis l'URL et l'affiche dans le conteneur."""
        try:
            # Sécurité : Limiter la taille des images pour ne pas surcharger la GUI
            TARGET_SIZE = (120, 120) 

            response = requests.get(url, timeout=5)
            response.raise_for_status() 
            image_data = Image.open(BytesIO(response.content))
            
            # Redimensionnement
            image_data.thumbnail(TARGET_SIZE)
            
            # Conversion au format Tkinter
            photo = ImageTk.PhotoImage(image_data)
            
            image_label = tk.Label(container, image=photo, relief='solid', borderwidth=1, background='white')
            image_label.pack(side='left', padx=5, pady=5)
            
            # ⭐ ESSENTIEL : Conserver la référence de l'objet PhotoImage
            self.photo_refs.append(photo) 
            
        except requests.exceptions.RequestException as e:
            placeholder = ttk.Label(container, text="[Image non disponible]", width=15, height=6, anchor='center', foreground='#8B0000', background='#F0F0F0')
            placeholder.pack(side='left', padx=5, pady=5)
        except Exception as e:
            placeholder = ttk.Label(container, text="[Erreur Image]", width=15, height=6, anchor='center', foreground='#8B0000', background='#F0F0F0')
            placeholder.pack(side='left', padx=5, pady=5)


    # --- Fonctions Bot (inchangées) ---

    def construire_url(self, marque):
        marque_encoded = quote_plus(marque.strip()) 
        final_url = f"{URL_BASE_FILTREE}&search_text={marque_encoded}"
        return final_url

    def initialiser_driver(self):
        try:
            self.log_message("Initialisation en cours...", 'status')
            
            options = webdriver.ChromeOptions()
            options.add_argument("--headless")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            
            self.service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=self.service, options=options)
            return True
        except Exception as e:
            self.log_message(f"❌ Erreur critique : {e}", 'status')
            self.is_running = False
            return False

    def accepter_cookies(self):
        try:
            cookie_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button[data-testid='cookie-banner-accept-all-button']")
            if cookie_buttons:
                cookie_buttons[0].click()
                time.sleep(2) 
                return True
        except Exception:
            try:
                 cookie_buttons = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Accepter tout') or contains(text(), 'Tout accepter')]")
                 if cookie_buttons:
                    cookie_buttons[0].click()
                    time.sleep(2)
                    return True
            except Exception:
                return False
        return False


    def bot_loop(self):
        marque = self.marque_entry.get().strip()
        if not marque:
            self.log_message("Veuillez entrer une marque.")
            self.stop_bot()
            return

        final_url = self.construire_url(marque)
        if not self.driver and not self.initialiser_driver(): return

        while self.is_running:
            start_time = time.time()
            
            try:
                self.status_label.config(text=f"Actif : {marque}", foreground=ACCENT_COLOR_ALERTE)
                
                self.driver.get(final_url)
                self.accepter_cookies()
                time.sleep(random.uniform(10, 15))
                
                articles = self.driver.find_elements(By.CSS_SELECTOR, SELECTEUR_ARTICLE)
                list_nouveaux_articles = []
                
                # 1. Extraction et identification de TOUS les nouveaux articles
                if articles:
                    for article in articles:
                        try:
                            prix_element = article.find_element(By.CSS_SELECTOR, SELECTEUR_PRIX)
                            image_element = article.find_element(By.CSS_SELECTOR, SELECTEUR_IMAGE_ALT)
                            lien_element = article.find_element(By.CSS_SELECTOR, SELECTEUR_LIEN)
                            
                            prix = prix_element.text.strip()
                            titre_complet = image_element.get_attribute('alt')
                            lien = lien_element.get_attribute('href')
                            photo_url = image_element.get_attribute('src')
                            
                            if not titre_complet: titre_complet = "Description non trouvée"

                            cle_article = f"{titre_complet}|{prix}|{lien}" 

                            if cle_article not in self.articles_deja_vus:
                                self.articles_deja_vus.add(cle_article)
                                list_nouveaux_articles.append({'titre': titre_complet, 'prix': prix, 'lien': lien, 'photo_url': photo_url})
                                
                        except NoSuchElementException:
                             continue 
                        except Exception as e:
                            self.log_message(f"Erreur d'extraction: {e}")
                            continue
                
                
                nouveaux_articles_trouves = len(list_nouveaux_articles)
                
                if nouveaux_articles_trouves == 0 and articles:
                    self.log_message(f"Aucun nouvel article depuis la dernière vérification.")
                elif nouveaux_articles_trouves > 0:
                    self.log_message(f"🎉 {nouveaux_articles_trouves} Nouveaux articles trouvés pour {marque}. Début de l'affichage par lots.")

                    # 2. Traitement des articles par lots de 10
                    for i in range(0, nouveaux_articles_trouves, TAILLE_BATCH):
                        
                        batch = list_nouveaux_articles[i:i + TAILLE_BATCH]
                        
                        for item in batch:
                            # ⭐ NOUVEAU : Affichage de l'article avec photo
                            self.display_article(item)
                        
                        # 3. Pause de 10 secondes entre les lots
                        if self.is_running and (i + TAILLE_BATCH) < nouveaux_articles_trouves:
                            self.log_message(f"... Affichage du prochain lot de {TAILLE_BATCH} dans {DELAI_BATCH_PROCESSING} secondes ...")
                            for t in range(DELAI_BATCH_PROCESSING):
                                if not self.is_running: break
                                time.sleep(1) 
                        elif nouveaux_articles_trouves > 0:
                            self.log_message(f"Tous les {nouveaux_articles_trouves} articles ont été affichés.")

                # 4. Calcul du temps d'attente restant
                end_time = time.time()
                time_elapsed = end_time - start_time
                delai_restant = DELAI_RAFRAICHISSEMENT - time_elapsed
                wait_time = max(5, delai_restant) 
                
                self.log_message(f"Prochaine vérification dans {int(wait_time)} secondes.")
                
                for i in range(int(wait_time)):
                    if not self.is_running: break
                    time.sleep(1) 
                
            except Exception as e:
                self.log_message(f"❌ Erreur générale: {e}")
                time.sleep(5) 

        if self.driver:
            self.driver.quit()
        self.status_label.config(text="Arrêté", foreground="black")

    def open_link(self, url):
        """Ouvre le lien dans le navigateur par défaut."""
        webbrowser.open_new(url)
        
    def start_bot(self):
        if not self.is_running:
            self.is_running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.articles_deja_vus.clear() 
            
            # Vider les références de photos avant un nouveau cycle
            self.photo_refs = [] 
            
            # Vider l'affichage en effaçant tous les widgets du frame intérieur
            for widget in self.log_scrollable_frame.interior.winfo_children():
                widget.destroy()

            self.log_message("Démarrage de la recherche...", 'status')
            
            self.bot_thread = threading.Thread(target=self.bot_loop)
            self.bot_thread.daemon = True 
            self.bot_thread.start()

    def stop_bot(self):
        if self.is_running:
            self.is_running = False
            self.status_label.config(text="Arrêt en cours...", foreground="orange")
            
if __name__ == "__main__":
    app = VintedBotGUI()
    def on_closing():
        app.stop_bot()
        if app.driver:
            app.driver.quit()
        app.destroy()
    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()
