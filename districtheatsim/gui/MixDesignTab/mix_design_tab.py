import pandas as pd
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QProgressBar, QTabWidget, QMessageBox, QFileDialog, QMenuBar, QScrollArea, QAction
from PyQt5.QtCore import pyqtSignal, QEventLoop

from heat_generators.heat_generator_classes import *
from gui.MixDesignTab.mix_design_dialogs import EconomicParametersDialog, NetInfrastructureDialog, TemperatureDataDialog, HeatPumpDataDialog
from gui.threads import CalculateMixThread
from gui.results_pdf import create_pdf

from gui.MixDesignTab.technology_tab import TechnologyTab
from gui.MixDesignTab.cost_tab import CostTab
from gui.MixDesignTab.results_tab import ResultsTab
from gui.MixDesignTab.sensitivity_tab import SensitivityTab

class MixDesignTab(QWidget):
    data_added = pyqtSignal(object)  # Signal, das Daten als Objekt überträgt
    
    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.results = {}
        self.tech_objects = []
        
        self.initDialogs()
        self.setupParameters()
        self.initUI()

        # Connect to the data manager signal
        self.data_manager.project_folder_changed.connect(self.updateDefaultPath)
        self.updateDefaultPath(self.data_manager.project_folder)

    def initDialogs(self):
        self.economicParametersDialog = EconomicParametersDialog(self)
        self.netInfrastructureDialog = NetInfrastructureDialog(self)
        self.temperatureDataDialog = TemperatureDataDialog(self)
        self.heatPumpDataDialog = HeatPumpDataDialog(self)

    def updateDefaultPath(self, new_base_path):
        self.base_path = new_base_path
        self.netInfrastructureDialog.base_path = self.base_path

    def initUI(self):
        self.createMainScrollArea()
        self.createMenu()
        self.createTabs()
        self.createProgressBar()
        self.setLayout(self.createMainLayout())

    def createMainScrollArea(self):
        self.mainScrollArea = QScrollArea(self)
        self.mainScrollArea.setWidgetResizable(True)
        self.mainWidget = QWidget()
        self.mainLayout = QVBoxLayout(self.mainWidget)
        self.mainScrollArea.setWidget(self.mainWidget)

    def createMenu(self):
        self.menuBar = QMenuBar(self)
        self.menuBar.setFixedHeight(30)

        # 'Datei'-Menü
        fileMenu = self.menuBar.addMenu('Datei')
        pdfAction = QAction('Ergebnisse als PDF speichern', self)
        pdfAction.triggered.connect(self.on_export_pdf_clicked)
        fileMenu.addAction(pdfAction)

        # 'Einstellungen'-Menü
        settingsMenu = self.menuBar.addMenu('Einstellungen')
        settingsMenu.addAction(self.createAction('Wirtschaftliche Parameter...', self.openEconomicParametersDialog))
        settingsMenu.addAction(self.createAction('Infrastrukturkosten...', self.openInfrastructureCostsDialog))
        settingsMenu.addAction(self.createAction('Temperaturdaten...', self.opentemperatureDataDialog))
        settingsMenu.addAction(self.createAction('COP-Kennfeld Wärmepumpe...', self.openheatPumpDataDialog))

        addHeatGeneratorMenu = self.menuBar.addMenu('Wärmeerzeuger hinzufügen')

        heatGenerators = ["Solarthermie", "BHKW", "Holzgas-BHKW", "Geothermie", "Abwärme", "Flusswasser", "Biomassekessel", "Gaskessel"]
        for generator in heatGenerators:
            action = QAction(generator, self)
            action.triggered.connect(lambda checked, gen=generator: self.techTab.addTech(gen, None))
            addHeatGeneratorMenu.addAction(action)

        # 'Berechnungen'-Menü
        calculationsMenu = self.menuBar.addMenu('Berechnungen')
        calculationsMenu.addAction(self.createAction('Berechnen', self.start_calculation))
        calculationsMenu.addAction(self.createAction('Optimieren', self.optimize))
        #calculationsMenu.addAction(self.createAction('Sensivitätsuntersuchung', self.sensitivity))

        # 'weitere Ergebnisse Anzeigen'-Menü
        showAdditionalResultsMenu = self.menuBar.addMenu('weitere Ergebnisse Anzeigen')
        showAdditionalResultsMenu.addAction(self.createAction('Kostenzusammensetzung über Betrachtungszeitraum', self.show_additional_results))

        self.mainLayout.addWidget(self.menuBar)

    def createAction(self, title, method):
        action = QAction(title, self)
        action.triggered.connect(method)
        return action

    def createTabs(self):
        self.tabWidget = QTabWidget()
        self.techTab = TechnologyTab(self.data_manager, self)
        self.costTab = CostTab(self.data_manager, self)
        self.resultTab = ResultsTab(self.data_manager, self)
        self.sensitivityTab = SensitivityTab(self.data_manager, self)
        self.tabWidget.addTab(self.techTab, "Erzeugerdefinition")
        self.tabWidget.addTab(self.costTab, "Kostenübersicht")
        self.tabWidget.addTab(self.resultTab, "Ergebnisse")
        self.tabWidget.addTab(self.sensitivityTab, "Sensivitätsuntersuchung")
        self.mainLayout.addWidget(self.tabWidget)

    def createProgressBar(self):
        self.progressBar = QProgressBar(self)
        self.mainLayout.addWidget(self.progressBar)

    def createMainLayout(self):
        layout = QVBoxLayout(self)
        layout.addWidget(self.menuBar)
        layout.addWidget(self.mainScrollArea)
        return layout

    ### Eingabe wirtschaftliche Randbedingungen ###
    def setupParameters(self):
        self.updateEconomicParameters()
        self.updateTemperatureData()
        self.updateHeatPumpData()

    def updateEconomicParameters(self):
        values = self.economicParametersDialog.getValues()
        self.gaspreis = values['Gaspreis in €/MWh']
        self.strompreis = values['Strompreis in €/MWh']
        self.holzpreis = values['Holzpreis in €/MWh']
        self.BEW = values['BEW-Förderung']
        self.kapitalzins = values['Kapitalzins in %']
        self.preissteigerungsrate = values['Preissteigerungsrate in %']
        self.betrachtungszeitraum = values['Betrachtungszeitraum in a']
        self.stundensatz = values['Stundensatz in €/h']

    def updateTemperatureData(self):
        TRY = self.temperatureDataDialog.getValues()
        self.try_filename = TRY['TRY-filename']

    def updateHeatPumpData(self):
        COP = self.heatPumpDataDialog.getValues()
        self.cop_filename = COP['COP-filename']

    ### Dialoge ###
    def openEconomicParametersDialog(self):
        if self.economicParametersDialog.exec_():
            self.updateEconomicParameters()
            #self.costTab.updateInfrastructureTable()
            #self.costTab.plotCostComposition()
            #self.costTab.updateSumLabel()

    def openInfrastructureCostsDialog(self):
        if self.netInfrastructureDialog.exec_():
            self.costTab.updateInfrastructureTable()
            self.costTab.plotCostComposition()
            self.costTab.updateSumLabel()

    def opentemperatureDataDialog(self):
        if self.temperatureDataDialog.exec_():
            self.updateTemperatureData()

    def openheatPumpDataDialog(self):
        if self.heatPumpDataDialog.exec_():
            self.updateHeatPumpData()

    ### Berechnungsfunktionen ###
    def validateInputs(self):
        try:
            load_scale_factor = float(self.techTab.load_scale_factorInput.text())
            if load_scale_factor <= 0:
                raise ValueError("Der Skalierungsfaktor muss größer als 0 sein.")
        except ValueError as e:
            QMessageBox.warning(self, "Ungültige Eingabe", str(e))
            return False
        return True

    def start_calculation(self, optimize=False):
        if not self.validateInputs():
            return

        if self.techTab.tech_objects:
            filename = self.techTab.FilenameInput.text()
            load_scale_factor = float(self.techTab.load_scale_factorInput.text())

            self.calculationThread = CalculateMixThread(
                filename, load_scale_factor, self.try_filename, self.cop_filename, self.gaspreis, 
                self.strompreis, self.holzpreis, self.BEW, self.techTab.tech_objects, optimize, 
                self.kapitalzins, self.preissteigerungsrate, self.betrachtungszeitraum, self.stundensatz)
            
            self.calculationThread.calculation_done.connect(self.on_calculation_done)
            self.calculationThread.calculation_error.connect(self.on_calculation_error)
            self.calculationThread.start()
            self.progressBar.setRange(0, 0)
        else:
            QMessageBox.information(self, "Keine Erzeugeranlagen", "Es wurden keine Erzeugeranlagen definiert. Keine Berechnung möglich.")

    def on_calculation_done(self, result):
        self.progressBar.setRange(0, 1)
        self.results, waerme_ges_kW, strom_wp_kW = result
        self.techTab.updateTechList()
        self.costTab.updateInfrastructureTable()  # Hier sicherstellen, dass zuerst die Infrastrukturtabelle aktualisiert wird
        self.costTab.updateTechDataTable(self.techTab.tech_objects)  # Danach die Tech-Tabelle aktualisieren
        self.costTab.updateSumLabel()  # Danach das Summenlabel aktualisieren
        self.costTab.plotCostComposition()
        self.resultTab.showResultsInTable(self.results)
        self.resultTab.showAdditionalResultsTable(self.results, waerme_ges_kW, strom_wp_kW)
        self.resultTab.plotResults(self.results)
        self.save_results_to_csv(self.results)
        self.showConfirmationDialog()

    def on_calculation_error(self, error_message):
        self.progressBar.setRange(0, 1)
        QMessageBox.critical(self, "Berechnungsfehler", str(error_message))

    def showConfirmationDialog(self):
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText(f"Die Berechnung des Erzeugermixes war erfolgreich. Die Ergebnisse wurden unter {self.base_path}\Lastgang\\results.csv gespeichert.")
        msgBox.setWindowTitle("Berechnung Erfolgreich")
        msgBox.setStandardButtons(QMessageBox.Ok)
        msgBox.exec_()

    def show_additional_results(self):
        if self.tech_objects and self.results:
            msgBox = QMessageBox()
            msgBox.setIcon(QMessageBox.Information)
            msgBox.setText(f"Hier gibts noch nichts zu sehen. Nur Konsolenausgabe.")
            msgBox.setWindowTitle("Hier könnten Ergebnisse Visualisiert werden.")
            msgBox.setStandardButtons(QMessageBox.Ok)
            msgBox.exec_()
            print(self.results)
            print(self.tech_objects)
        else:
            QMessageBox.information(self, "Keine Berechnungsergebnisse", "Es sind keine Berechnungsergebnisse verfügbar. Führen Sie zunächst eine Berechnung durch.")

    def optimize(self):
        self.start_calculation(True)

    ### NEU !!! ###
    def sensitivity(self, gas_range, electricity_range, wood_range):
        if not self.validateInputs():
            return

        if not self.techTab.tech_objects:
            QMessageBox.information(self, "Keine Erzeugeranlagen", "Es wurden keine Erzeugeranlagen definiert. Keine Berechnung möglich.")
            return

        filename = self.techTab.FilenameInput.text()
        load_scale_factor = float(self.techTab.load_scale_factorInput.text())

        results = []
        for gas_price in self.generate_values(gas_range):
            for electricity_price in self.generate_values(electricity_range):
                for wood_price in self.generate_values(wood_range):
                    result, waerme_ges_kW, strom_wp_kW = self.calculate_mix(filename, load_scale_factor, gas_price, electricity_price, wood_price)
                    waerme_ges_kW, strom_wp_kW = np.sum(waerme_ges_kW), np.sum(strom_wp_kW)
                    wgk_heat_pump_electricity = ((strom_wp_kW/1000) * electricity_price) / ((strom_wp_kW+waerme_ges_kW)/1000)
                    if result is not None:
                        results.append({
                            'gas_price': gas_price,
                            'electricity_price': electricity_price,
                            'wood_price': wood_price,
                            'WGK_Gesamt': result['WGK_Gesamt'],
                            'waerme_ges_kW': waerme_ges_kW,
                            'strom_wp_kW': strom_wp_kW,
                            'wgk_heat_pump_electricity': wgk_heat_pump_electricity
                        })

        self.sensitivityTab.plotSensitivity(results)
        self.sensitivityTab.plotSensitivitySurface(results)

    def generate_values(self, price_range):
        lower, upper, num_points = price_range
        step = (upper - lower) / (num_points - 1)
        return [lower + i * step for i in range(num_points)]

    def calculate_mix(self, filename, load_scale_factor, gas_price, electricity_price, wood_price):
        result = None
        calculation_done_event = QEventLoop()
        
        def calculation_done(result_data):
            self.progressBar.setRange(0, 1)
            nonlocal result
            result = result_data
            calculation_done_event.quit()

        def calculation_error(error_message):
            self.progressBar.setRange(0, 1)
            QMessageBox.critical(self, "Berechnungsfehler", str(error_message))
            calculation_done_event.quit()

        self.calculationThread = CalculateMixThread(
            filename, load_scale_factor, self.try_filename, self.cop_filename, gas_price, 
            electricity_price, wood_price, self.BEW, self.techTab.tech_objects, False, 
            self.kapitalzins, self.preissteigerungsrate, self.betrachtungszeitraum, self.stundensatz)
        
        self.calculationThread.calculation_done.connect(calculation_done)
        self.calculationThread.calculation_error.connect(calculation_error)
        self.calculationThread.start()
        self.progressBar.setRange(0, 0)
        calculation_done_event.exec_()  # Wait for the thread to finish

        # Ensure the thread has finished before returning
        self.calculationThread.wait()

        return result
    
    ### ###

    ### Speicherung der Berechnungsergebnisse der Erzeugerauslegung als csv ###
    def save_results_to_csv(self, results):
        # Initialisiere den DataFrame mit den Zeitstempeln
        df = pd.DataFrame({'time_steps': results['time_steps']})
        
        # Füge die Last hinzu
        df['Last_L'] = results['Last_L']
        
        # Füge die Daten für Wärmeleistung hinzu. Jede Technologie wird eine Spalte haben.
        for i, (tech_results, techs) in enumerate(zip(results['Wärmeleistung_L'], results['techs'])):
            df[techs] = tech_results
        
        # Füge die elektrischen Leistungsdaten hinzu
        df['el_Leistungsbedarf_L'] = results['el_Leistungsbedarf_L']
        df['el_Leistung_L'] = results['el_Leistung_L']
        df['el_Leistung_ges_L'] = results['el_Leistung_ges_L']
        
        # Speichere den DataFrame als CSV-Datei
        csv_filename = f"{self.base_path}\Lastgang\\results.csv"
        df.to_csv(csv_filename, index=False, sep=";")
        print(f"Ergebnisse wurden in '{csv_filename}' gespeichert.")

    def on_export_pdf_clicked(self):
        filename, _ = QFileDialog.getSaveFileName(self, 'PDF speichern als...', filter='PDF Files (*.pdf)')
        if filename:
            create_pdf(self, filename)
