"""
Filename: heat_generator_classes.py
Author: Dipl.-Ing. (FH) Jonas Pfeiffer
Date: 2024-07-31
Description: Contains the heat generator classes as well as the calculation and optimization functions for the heating system.

"""

import numpy as np
from math import pi, sqrt

from scipy.optimize import minimize
from scipy.interpolate import RegularGridInterpolator

import CoolProp.CoolProp as CP

from heat_generators.solar_thermal import Berechnung_STA
from heat_generators.photovoltaics import Calculate_PV

# Wirtschaftlichkeitsberechnung für technische Anlagen nach VDI 2067
def annuität(A0, TN, f_Inst, f_W_Insp, Bedienaufwand=0, q=1.05, r=1.03, T=20, Energiebedarf=0, Energiekosten=0, E1=0, stundensatz=45):
    """
    Calculate the annuity for a given set of parameters over a specified period.

    Args:
        A0 (float): Initial investment cost.
        TN (int): Useful life of the investment.
        f_Inst (float): Installation factor.
        f_W_Insp (float): Maintenance and inspection factor.
        Bedienaufwand (float, optional): Operating effort in hours. Defaults to 0.
        q (float, optional): Interest rate factor. Defaults to 1.05.
        r (float, optional): Inflation rate factor. Defaults to 1.03.
        T (int, optional): Consideration period in years. Defaults to 20.
        Energiebedarf (float, optional): Energy demand in kWh. Defaults to 0.
        Energiekosten (float, optional): Energy costs in €/kWh. Defaults to 0.
        E1 (float, optional): Annual revenue. Defaults to 0.
        stundensatz (float, optional): Hourly rate for labor in €/h. Defaults to 45.

    Returns:
        float: Calculated annuity value.
    """
    if T > TN:
        n = T // TN
    else:
        n = 0

    a = (q - 1) / (1 - (q ** (-T)))  # Annuitätsfaktor
    b = (1 - (r / q) ** T) / (q - r)  # preisdynamischer Barwertfaktor
    b_v = b_B = b_IN = b_s = b_E = b

    # kapitalgebundene Kosten
    AN = A0
    AN_L = [A0]
    for i in range(1, n+1):
        Ai = A0*((r**(n*TN))/(q**(n*TN)))
        AN += Ai
        AN_L.append(Ai)

    R_W = A0 * (r**(n*TN)) * (((n+1)*TN-T)/TN) * 1/(q**T)
    A_N_K = (AN - R_W) * a

    # bedarfsgebundene Kosten
    A_V1 = Energiebedarf * Energiekosten
    A_N_V = A_V1 * a * b_v

    # betriebsgebundene Kosten
    A_B1 = Bedienaufwand * stundensatz
    A_IN = A0 * (f_Inst + f_W_Insp)/100
    A_N_B = A_B1 * a * b_B + A_IN * a * b_IN

    # sonstige Kosten
    A_S1 = 0
    A_N_S = A_S1 * a * b_s

    A_N = - (A_N_K + A_N_V + A_N_B + A_N_S)  # Annuität

    # Erlöse
    A_NE = E1*a*b_E

    A_N += A_NE

    return -A_N

class HeatPump:
    """
    This class represents a Heat Pump and provides methods to calculate various performance and economic metrics.

    Attributes:
        name (str): The name of the heat pump.
        spezifische_Investitionskosten_WP (float): Specific investment costs of the heat pump per kW. Default is 1000.
        Nutzungsdauer_WP (int): Useful life of the heat pump in years. Default is 20.
        f_Inst_WP (float): Installation factor for the heat pump. Default is 1.
        f_W_Insp_WP (float): Maintenance and inspection factor for the heat pump. Default is 1.5.
        Bedienaufwand_WP (float): Operating effort in hours for the heat pump. Default is 0.
        f_Inst_WQ (float): Installation factor for the heat source. Default is 0.5.
        f_W_Insp_WQ (float): Maintenance and inspection factor for the heat source. Default is 0.5.
        Bedienaufwand_WQ (float): Operating effort in hours for the heat source. Default is 0.
        Nutzungsdauer_WQ_dict (dict): Dictionary containing useful life of different heat sources.
        co2_factor_electricity (float): CO2 emission factor for electricity in tCO2/MWh. Default is 2.4.

    Methods:
        COP_WP(VLT_L, QT, COP_data): Calculates the Coefficient of Performance (COP) of the heat pump.
        WGK(Wärmeleistung, Wärmemenge, Strombedarf, spez_Investitionskosten_WQ, Strompreis, q, r, T, BEW, stundensatz): Calculates the heat generation costs (WGK).
    """

    def __init__(self, name, spezifische_Investitionskosten_WP=1000):
        self.name = name
        self.spezifische_Investitionskosten_WP = spezifische_Investitionskosten_WP
        self.Nutzungsdauer_WP = 20
        self.f_Inst_WP, self.f_W_Insp_WP, self.Bedienaufwand_WP = 1, 1.5, 0
        self.f_Inst_WQ, self.f_W_Insp_WQ, self.Bedienaufwand_WQ = 0.5, 0.5, 0
        self.Nutzungsdauer_WQ_dict = {"Abwärme": 20, "Abwasserwärme": 20, "Flusswasser": 20, "Geothermie": 30}
        self.co2_factor_electricity = 2.4 # tCO2/MWh electricity

    def COP_WP(self, VLT_L, QT, COP_data):
        """
        Calculates the Coefficient of Performance (COP) of the heat pump using interpolation.

        Args:
            VLT_L (array-like): Flow temperatures.
            QT (float or array-like): Source temperatures.
            COP_data (array-like): COP data for interpolation.

        Returns:
            tuple: Interpolated COP values and adjusted flow temperatures.
        """

        # Interpolationsformel für den COP
        values = COP_data  # np.genfromtxt('Kennlinien WP.csv', delimiter=';')
        row_header = values[0, 1:]  # Vorlauftemperaturen
        col_header = values[1:, 0]  # Quelltemperaturen
        values = values[1:, 1:]
        f = RegularGridInterpolator((col_header, row_header), values, method='linear')

        # technische Grenze der Wärmepumpe ist Temperaturhub von 75 °C
        VLT_L = np.minimum(VLT_L, 75 + QT)

        # Überprüfen, ob QT eine Zahl oder ein Array ist
        if np.isscalar(QT):
            # Wenn QT eine Zahl ist, erstellen wir ein Array mit dieser Zahl
            QT_array = np.full_like(VLT_L, QT)
        else:
            # Wenn QT bereits ein Array ist, prüfen wir, ob es die gleiche Länge wie VLT_L hat
            if len(QT) != len(VLT_L):
                raise ValueError("QT muss entweder eine einzelne Zahl oder ein Array mit der gleichen Länge wie VLT_L sein.")
            QT_array = QT

        # Berechnung von COP_L
        COP_L = f(np.column_stack((QT_array, VLT_L)))

        return COP_L, VLT_L
    
    def WGK(self, Wärmeleistung, Wärmemenge, Strombedarf, spez_Investitionskosten_WQ, Strompreis, q, r, T, BEW, stundensatz):
        """
        Calculates the heat generation costs (WGK) of the heat pump.

        Args:
            Wärmeleistung (float): Heat output of the heat pump.
            Wärmemenge (float): Amount of heat produced.
            Strombedarf (float): Electricity demand.
            spez_Investitionskosten_WQ (float): Specific investment costs for the heat source.
            Strompreis (float): Price of electricity.
            q (float): Interest rate factor.
            r (float): Inflation rate factor.
            T (int): Consideration period in years.
            BEW (float): Discount rate.
            stundensatz (float): Hourly labor rate.

        Returns:
            float: Calculated heat generation costs.
        """

        if Wärmemenge == 0:
            return 0
        # Kosten Wärmepumpe: Viessmann Vitocal 350 HT-Pro: 140.000 €, 350 kW Nennleistung; 120 kW bei 10/85
        # Annahme Kosten Wärmepumpe: 1000 €/kW; Vereinfachung
        spezifische_Investitionskosten_WP = self.spezifische_Investitionskosten_WP
        Investitionskosten_WP = spezifische_Investitionskosten_WP * round(Wärmeleistung, 0)
        E1_WP = annuität(Investitionskosten_WP, self.Nutzungsdauer_WP, self.f_Inst_WP, self.f_W_Insp_WP, self.Bedienaufwand_WP, q, r, T,
                            Strombedarf, Strompreis, stundensatz=stundensatz)
        WGK_WP_a = E1_WP / Wärmemenge

        # Extrahieren des Basisnamens aus dem Namen des Erzeugers
        base_name = self.name.split('_')[0]
        
        # Überprüfen, ob der Basisname in Nutzungsdauer_WQ_dict vorhanden ist
        if base_name not in self.Nutzungsdauer_WQ_dict:
            raise KeyError(f"{base_name} ist kein gültiger Schlüssel in Nutzungsdauer_WQ_dict")
        
        Investitionskosten_WQ = spez_Investitionskosten_WQ * Wärmeleistung
        E1_WQ = annuität(Investitionskosten_WQ, self.Nutzungsdauer_WQ_dict[base_name], self.f_Inst_WQ, self.f_W_Insp_WQ,
                            self.Bedienaufwand_WQ, q, r, T, stundensatz=stundensatz)
        WGK_WQ_a = E1_WQ / Wärmemenge

        WGK_Gesamt_a = WGK_WP_a + WGK_WQ_a

        return WGK_Gesamt_a

class RiverHeatPump(HeatPump):
    """
    This class represents a River Heat Pump and provides methods to calculate various performance and economic metrics.

    Args:
        HeatPump (_type_): Base class for the heat pump.

    Attributes:
        Wärmeleistung_FW_WP (float): Heat output of the river water heat pump.
        Temperatur_FW_WP (float): Temperature of the river water.
        dT (float): Temperature difference. Default is 0.
        spez_Investitionskosten_Flusswasser (float): Specific investment costs for river water heat pump per kW. Default is 1000.
        spezifische_Investitionskosten_WP (float): Specific investment costs of the heat pump per kW. Default is 1000.
        min_Teillast (float): Minimum partial load. Default is 0.2.
        co2_factor_electricity (float): CO2 emission factor for electricity in tCO2/MWh. Default is 0.4.
        primärenergiefaktor (float): Primary energy factor. Default is 2.4.

    Methods:
        Berechnung_WP(Wärmeleistung_L, VLT_L, COP_data): Calculates the cooling load, electric power consumption, and adjusted flow temperatures.
        abwärme(Last_L, VLT_L, COP_data, duration): Calculates the waste heat and other performance metrics.
        calculate(VLT_L, COP_data, Strompreis, q, r, T, BEW, stundensatz, duration, general_results): Calculates the economic and environmental metrics for the heat pump.
        to_dict(): Converts the object attributes to a dictionary.
        from_dict(data): Creates an object from a dictionary of attributes.
    """
    def __init__(self, name, Wärmeleistung_FW_WP, Temperatur_FW_WP, dT=0, spez_Investitionskosten_Flusswasser=1000, spezifische_Investitionskosten_WP=1000, min_Teillast=0.2):
        super().__init__(name, spezifische_Investitionskosten_WP=spezifische_Investitionskosten_WP)
        self.Wärmeleistung_FW_WP = Wärmeleistung_FW_WP
        self.Temperatur_FW_WP = Temperatur_FW_WP
        self.dT = dT
        self.spez_Investitionskosten_Flusswasser = spez_Investitionskosten_Flusswasser
        self.min_Teillast = min_Teillast
        self.co2_factor_electricity = 0.4 # tCO2/MWh electricity
        self.primärenergiefaktor = 2.4

    def Berechnung_WP(self, Wärmeleistung_L, VLT_L, COP_data):
        """
        Calculates the cooling load, electric power consumption, and adjusted flow temperatures for the heat pump.

        Args:
            Wärmeleistung_L (array-like): Heat output load.
            VLT_L (array-like): Flow temperatures.
            COP_data (array-like): COP data for interpolation.

        Returns:
            tuple: Cooling load, electric power consumption, and adjusted flow temperatures.
        """
        COP_L, VLT_L_WP = self.COP_WP(VLT_L, self.Temperatur_FW_WP, COP_data)
        Kühlleistung_L = Wärmeleistung_L * (1 - (1 / COP_L))
        el_Leistung_L = Wärmeleistung_L - Kühlleistung_L
        return Kühlleistung_L, el_Leistung_L, VLT_L_WP

    # Änderung Kühlleistung und Temperatur zu Numpy-Array in aw sowie vor- und nachgelagerten Funktionen
    def abwärme(self, Last_L, VLT_L, COP_data, duration):
        """
        Calculates the waste heat and other performance metrics for the heat pump.

        Args:
            Last_L (array-like): Load demand.
            VLT_L (array-like): Flow temperatures.
            COP_data (array-like): COP data for interpolation.
            duration (float): Time duration.

        Returns:
            tuple: Heat energy, electricity demand, heat output, electric power, cooling energy, and cooling load.
        """
        if self.Wärmeleistung_FW_WP == 0:
            return 0, 0, np.zeros_like(Last_L), np.zeros_like(VLT_L), 0, np.zeros_like(VLT_L)

        Wärmeleistung_tat_L = np.zeros_like(Last_L)
        Kühlleistung_tat_L = np.zeros_like(Last_L)
        el_Leistung_tat_L = np.zeros_like(Last_L)
        VLT_L_WP = np.zeros_like(VLT_L)

        # Fälle, in denen die Wärmepumpe betrieben werden kann
        betrieb_mask = Last_L >= self.Wärmeleistung_FW_WP * self.min_Teillast
        Wärmeleistung_tat_L[betrieb_mask] = np.minimum(Last_L[betrieb_mask], self.Wärmeleistung_FW_WP)

        Kühlleistung_tat_L[betrieb_mask], el_Leistung_tat_L[betrieb_mask], VLT_L_WP[betrieb_mask] = self.Berechnung_WP(Wärmeleistung_tat_L[betrieb_mask], VLT_L[betrieb_mask], COP_data)

        # Wärmepumpe soll nur in Betrieb sein, wenn Sie die Vorlauftemperatur erreichen kann
        betrieb_mask_vlt = VLT_L_WP >= VLT_L - self.dT
        Wärmeleistung_tat_L[~betrieb_mask_vlt] = 0
        Kühlleistung_tat_L[~betrieb_mask_vlt] = 0
        el_Leistung_tat_L[~betrieb_mask_vlt] = 0

        Wärmemenge = np.sum(Wärmeleistung_tat_L / 1000) * duration
        Kühlmenge = np.sum(Kühlleistung_tat_L / 1000) * duration
        Strombedarf = np.sum(el_Leistung_tat_L / 1000) * duration

        return Wärmemenge, Strombedarf, Wärmeleistung_tat_L, el_Leistung_tat_L, Kühlmenge, Kühlleistung_tat_L
    
    def calculate(self,VLT_L, COP_data, Strompreis, q, r, T, BEW, stundensatz, duration, general_results):
        """
        Calculates the economic and environmental metrics for the river heat pump.

        Args:
            VLT_L (array-like): Flow temperatures.
            COP_data (array-like): COP data for interpolation.
            Strompreis (float): Price of electricity.
            q (float): Interest rate factor.
            r (float): Inflation rate factor.
            T (int): Consideration period in years.
            BEW (float): Discount rate.
            stundensatz (float): Hourly labor rate.
            duration (float): Time duration.
            general_results (dict): Dictionary containing general results and metrics.

        Returns:
            dict: Dictionary containing calculated metrics and results.
        """
        
        self.Wärmemenge_Flusswärme, self.Strombedarf_Flusswärme, self.Wärmeleistung_kW, self.el_Leistung_kW, self.Kühlmenge_Flusswärme, self.Kühlleistung_Flusswärme_L = self.abwärme(general_results["Restlast_L"], VLT_L, COP_data, duration)

        WGK_Abwärme = self.WGK(self.Wärmeleistung_FW_WP, self.Wärmemenge_Flusswärme, self.Strombedarf_Flusswärme, self.spez_Investitionskosten_Flusswasser, Strompreis, q, r, T, BEW, stundensatz)

        # CO2 emissions due to fuel usage
        self.co2_emissions = self.Strombedarf_Flusswärme * self.co2_factor_electricity # tCO2
        # specific emissions heat
        self.spec_co2_total = self.co2_emissions / self.Wärmemenge_Flusswärme if self.Wärmemenge_Flusswärme > 0 else 0 # tCO2/MWh_heat

        self.primärenergie = self.Strombedarf_Flusswärme * self.primärenergiefaktor

        results = {
            'Wärmemenge': self.Wärmemenge_Flusswärme,
            'Wärmeleistung_L': self.Wärmeleistung_kW,
            'Strombedarf': self.Strombedarf_Flusswärme,
            'el_Leistung_L': self.el_Leistung_kW,
            'WGK': WGK_Abwärme,
            'spec_co2_total': self.spec_co2_total,
            'primärenergie': self.primärenergie,
            'color': "blue"
        }

        return results

    def to_dict(self):
        """
        Converts the object attributes to a dictionary.

        Returns:
            dict: Dictionary containing object attributes.
        """
        return self.__dict__
    
    @staticmethod
    def from_dict(data):
        """
        Creates an object from a dictionary of attributes.

        Args:
            data (dict): Dictionary containing object attributes.

        Returns:
            RiverHeatPump: Created object from the given dictionary.
        """
        obj = RiverHeatPump.__new__(RiverHeatPump)
        obj.__dict__.update(data)
        return obj


# AqvaHeat Simulation
class AqvaHeat(HeatPump):
    """
    This class represents a AqvaHeat-solution (vacuum ice slurry generator with attached heat pump) and provides methods to calculate various performance and economic metrics.

    Args:
        HeatPump (_type_): Base class for the heat pump.

    Attributes:
        Wärmeleistung_FW_WP (float): Heat output of the river water heat pump.
        Temperatur_FW_WP (float): Temperature of the river water.
        dT (float): Temperature difference. Default is 0.
        spez_Investitionskosten_Flusswasser (float): Specific investment costs for river water heat pump per kW. Default is 1000.
        spezifische_Investitionskosten_WP (float): Specific investment costs of the heat pump per kW. Default is 1000.
        min_Teillast (float): Minimum partial load. Default is 0.2.
        co2_factor_electricity (float): CO2 emission factor for electricity in tCO2/MWh. Default is 0.4.
        primärenergiefaktor (float): Primary energy factor. Default is 2.4.

    Methods:
        Berechnung_WP(Wärmeleistung_L, VLT_L, COP_data): Calculates the cooling load, electric power consumption, and adjusted flow temperatures.
        abwärme(Last_L, VLT_L, COP_data, duration): Calculates the waste heat and other performance metrics.
        calculate(VLT_L, COP_data, Strompreis, q, r, T, BEW, stundensatz, duration, general_results): Calculates the economic and environmental metrics for the heat pump.
        to_dict(): Converts the object attributes to a dictionary.
        from_dict(data): Creates an object from a dictionary of attributes.
    """
    def __init__(self, name, nominal_power=100, temperature_difference=0):

        self.name = name
        self.nominal_power = nominal_power
        self.min_partial_load = 1  # no partial load for now (0..1)
        self.temperature_difference = 2.5  # difference over heat exchanger
        self.primärenergiefaktor = 2.4
        self.Wärmeleistung_FW_WP = nominal_power


    def calculate(self, output_temperatures, COP_data, duration, general_results):

        residual_powers = general_results["Restlast_L"]
        effective_powers = np.zeros_like(residual_powers)

        intermediate_temperature = 12  # °C

        # calculate power in time steps where operation of aggregate is possible due to minimal partial load
        operation_mask = residual_powers >= self.nominal_power * self.min_partial_load
        effective_powers[operation_mask] = np.minimum(residual_powers[operation_mask], self.nominal_power)

        # HEAT PUMP
        # calculate first the heat pump (from 12°C to supply temperature)
        COP, effective_output_temperatures = self.COP_WP(output_temperatures, intermediate_temperature, COP_data)
        cooling_powers = effective_powers * (1 - (1 / COP))
        electrical_powers = effective_powers - cooling_powers

        # disable heat pump when not reaching supply temperature
        operation_mask = effective_output_temperatures >= output_temperatures - self.temperature_difference  # TODO: verify direction of difference
        effective_powers[~operation_mask] = 0
        cooling_powers[~operation_mask] = 0
        electrical_powers[~operation_mask] = 0

        # sum energy over whole lifetime
        # convert to MWh
        heat_supplied = np.sum(effective_powers / 1000) * duration
        cooling_supplied = np.sum(cooling_powers / 1000) * duration

        # VACUUM ICE GENERATOR
        # now the vacuum ice generator, needs to supply 12°C from river water to the heatpump
        # cooling supplied by heat pump is heat supplied by vacuum ice process 

        isentropic_efficiency = 0.7  # Adjust this value based on the actual compressor efficiency
        fluid = 'Water'
        molar_mass_water = 18.01528  # in g/mol

        # Triple point conditions for water
        # temperature_triple_point = 273.16  # Temperature in Kelvin
        # pressure_triple_point = 611.657  # Pressure in Pascal

        # Define initial conditions
        triple_point_pressure =  CP.PropsSI('ptriple', 'T', 0, 'P', 0, fluid) + 0.01 # in Pascal, delta because of validity range
        triple_point_temperature = CP.PropsSI('T', 'Q', 0, 'P', triple_point_pressure + 1, fluid)  # Triple point temperature

        initial_pressure = triple_point_pressure
        initial_temperature = triple_point_temperature

        # Define final conditions after first compression
        final_temperature = 12 + 273.15  # Convert to Kelvin
        final_pressure = CP.PropsSI('P', 'T', final_temperature, 'Q', 0, fluid)

        # mass flow from condensing vapor at 12°C, 14hPa
        mass_flows = effective_powers / (CP.PropsSI('H','P',14000,'Q',1,'Water') - 
                                        CP.PropsSI('H','P',14000,'Q',0,'Water'))
        # electrical power needed compressing vapor from triple point 
        energy_compression = (CP.PropsSI('H', 'T', final_temperature, 'P', final_pressure, fluid) -
                                      CP.PropsSI('H', 'T', initial_temperature, 'P', initial_pressure, fluid)) / isentropic_efficiency

        electrical_powers += mass_flows * energy_compression / 1000  # W -> kW

        self.Wärmemenge_AqvaHeat = heat_supplied
        self.Wärmeleistung_kW = effective_powers

        electricity_consumed = np.sum(electrical_powers / 1000) * duration
        self.Strombedarf_AqvaHeat = electricity_consumed

        self.el_Leistung_kW = electrical_powers

        WGK_Abwärme = -1
        self.primärenergie = self.Strombedarf_AqvaHeat * self.primärenergiefaktor

        self.spec_co2_total = -1


        results = {
            'Wärmemenge': self.Wärmemenge_AqvaHeat,  # heat energy for whole duration
            'Wärmeleistung_L': self.Wärmeleistung_kW,  # vector length time steps with actual power supplied
            'Strombedarf': self.Strombedarf_AqvaHeat,  # electrical energy consumed during whole duration
            'el_Leistung_L': self.el_Leistung_kW,  # vector length time steps with actual electrical power consumed
            'WGK': WGK_Abwärme,
            'spec_co2_total': self.spec_co2_total,  # tCO2/MWh_heat
            'primärenergie': self.primärenergie,
            'color': "blue"
        }

        return results

    def to_dict(self):
        """
        Converts the object attributes to a dictionary.

        Returns:
            dict: Dictionary containing object attributes.
        """
        return self.__dict__

    @staticmethod
    def from_dict(data):
        """
        Creates an object from a dictionary of attributes.

        Args:
            data (dict): Dictionary containing object attributes.

        Returns:
            Geothermal: Created object from the given dictionary.
        """
        obj = Geothermal.__new__(Geothermal)
        obj.__dict__.update(data)
        return obj


class WasteHeatPump(HeatPump):
    """
    This class represents a Waste Heat Pump and provides methods to calculate various performance and economic metrics.

    Args:
        HeatPump (_type_): Base class for the heat pump.

    Attributes:
        Kühlleistung_Abwärme (float): Cooling capacity of the waste heat pump.
        Temperatur_Abwärme (float): Temperature of the waste heat.
        spez_Investitionskosten_Abwärme (float): Specific investment costs for waste heat pump per kW. Default is 500.
        spezifische_Investitionskosten_WP (float): Specific investment costs of the heat pump per kW. Default is 1000.
        min_Teillast (float): Minimum partial load. Default is 0.2.
        co2_factor_electricity (float): CO2 emission factor for electricity in tCO2/MWh. Default is 0.4.
        primärenergiefaktor (float): Primary energy factor. Default is 2.4.

    Methods:
        Berechnung_WP(VLT_L, COP_data): Calculates the heat load, electric power consumption, and adjusted flow temperatures.
        abwärme(Last_L, VLT_L, COP_data, duration): Calculates the waste heat and other performance metrics.
        calculate(VLT_L, COP_data, Strompreis, q, r, T, BEW, stundensatz, duration, general_results): Calculates the economic and environmental metrics for the heat pump.
        to_dict(): Converts the object attributes to a dictionary.
        from_dict(data): Creates an object from a dictionary of attributes.
    """
    def __init__(self, name, Kühlleistung_Abwärme, Temperatur_Abwärme, spez_Investitionskosten_Abwärme=500, spezifische_Investitionskosten_WP=1000, min_Teillast=0.2):
        super().__init__(name, spezifische_Investitionskosten_WP=spezifische_Investitionskosten_WP)
        self.Kühlleistung_Abwärme = Kühlleistung_Abwärme
        self.Temperatur_Abwärme = Temperatur_Abwärme
        self.spez_Investitionskosten_Abwärme = spez_Investitionskosten_Abwärme
        self.min_Teillast = min_Teillast
        self.co2_factor_electricity = 0.4 # tCO2/MWh electricity
        self.primärenergiefaktor = 2.4

    def Berechnung_WP(self, VLT_L, COP_data):
        """
        Calculates the heat load, electric power consumption, and adjusted flow temperatures for the waste heat pump.

        Args:
            VLT_L (array-like): Flow temperatures.
            COP_data (array-like): COP data for interpolation.

        Returns:
            tuple: Heat load, electric power consumption.
        """
        COP_L, VLT_L = self.COP_WP(VLT_L, self.Temperatur_Abwärme, COP_data)
        Wärmeleistung_L = self.Kühlleistung_Abwärme / (1 - (1 / COP_L))
        el_Leistung_L = Wärmeleistung_L - self.Kühlleistung_Abwärme
        return Wärmeleistung_L, el_Leistung_L

    def abwärme(self, Last_L, VLT_L, COP_data, duration):
        """
        Calculates the waste heat and other performance metrics for the waste heat pump.

        Args:
            Last_L (array-like): Load demand.
            VLT_L (array-like): Flow temperatures.
            COP_data (array-like): COP data for interpolation.
            duration (float): Time duration.

        Returns:
            tuple: Heat energy, electricity demand, heat output, electric power.
        """
        if self.Kühlleistung_Abwärme == 0:
            return 0, 0, np.zeros_like(Last_L), np.zeros_like(VLT_L)

        Wärmeleistung_L, el_Leistung_L = self.Berechnung_WP(VLT_L, COP_data)

        Wärmeleistung_tat_L = np.zeros_like(Last_L)
        el_Leistung_tat_L = np.zeros_like(Last_L)

        # Cases where the heat pump can be operated
        betrieb_mask = Last_L >= Wärmeleistung_L * self.min_Teillast
        Wärmeleistung_tat_L[betrieb_mask] = np.minimum(Last_L[betrieb_mask], Wärmeleistung_L[betrieb_mask])
        el_Leistung_tat_L[betrieb_mask] = Wärmeleistung_tat_L[betrieb_mask] - (Wärmeleistung_tat_L[betrieb_mask] / Wärmeleistung_L[betrieb_mask]) * el_Leistung_L[betrieb_mask]

        Wärmemenge = np.sum(Wärmeleistung_tat_L / 1000) * duration
        Strombedarf = np.sum(el_Leistung_tat_L / 1000) * duration

        self.max_Wärmeleistung = np.max(Wärmeleistung_tat_L)

        return Wärmemenge, Strombedarf, Wärmeleistung_tat_L, el_Leistung_tat_L
    
    def calculate(self, VLT_L, COP_data, Strompreis, q, r, T, BEW, stundensatz, duration, general_results):
        """
        Calculates the economic and environmental metrics for the waste heat pump.

        Args:
            VLT_L (array-like): Flow temperatures.
            COP_data (array-like): COP data for interpolation.
            Strompreis (float): Price of electricity.
            q (float): Interest rate factor.
            r (float): Inflation rate factor.
            T (int): Consideration period in years.
            BEW (float): Discount rate.
            stundensatz (float): Hourly labor rate.
            duration (float): Time duration.
            general_results (dict): Dictionary containing general results and metrics.

        Returns:
            dict: Dictionary containing calculated metrics and results.
        """
        self.Wärmemenge_Abwärme, self.Strombedarf_Abwärme, self.Wärmeleistung_kW, self.el_Leistung_kW = self.abwärme(general_results['Restlast_L'], VLT_L, COP_data, duration)

        WGK_Abwärme = self.WGK(self.max_Wärmeleistung, self.Wärmemenge_Abwärme, self.Strombedarf_Abwärme, self.spez_Investitionskosten_Abwärme, Strompreis, q, r, T, BEW, stundensatz)

        # CO2 emissions due to fuel usage
        self.co2_emissions = self.Strombedarf_Abwärme * self.co2_factor_electricity # tCO2
        # specific emissions heat
        self.spec_co2_total = self.co2_emissions / self.Wärmemenge_Abwärme if self.Wärmemenge_Abwärme > 0 else 0 # tCO2/MWh_heat

        self.primärenergie = self.Strombedarf_Abwärme * self.primärenergiefaktor

        results = {
            'Wärmemenge': self.Wärmemenge_Abwärme,
            'Wärmeleistung_L': self.Wärmeleistung_kW,
            'Strombedarf': self.Strombedarf_Abwärme,
            'el_Leistung_L': self.el_Leistung_kW,
            'WGK': WGK_Abwärme,
            'spec_co2_total': self.spec_co2_total,
            'primärenergie': self.primärenergie,
            'color': "grey"
        }

        return results
    
    def to_dict(self):
        """
        Converts the object attributes to a dictionary.

        Returns:
            dict: Dictionary containing object attributes.
        """
        return self.__dict__

    @staticmethod
    def from_dict(data):
        """
        Creates an object from a dictionary of attributes.

        Args:
            data (dict): Dictionary containing object attributes.

        Returns:
            WasteHeatPump: Created object from the given dictionary.
        """
        obj = WasteHeatPump.__new__(WasteHeatPump)
        obj.__dict__.update(data)
        return obj

class Geothermal(HeatPump):
    """
    This class represents a Geothermal Heat Pump and provides methods to calculate various performance and economic metrics.

    Args:
        HeatPump (_type_): Base class for the heat pump.

    Attributes:
        Fläche (float): Area available for geothermal installation.
        Bohrtiefe (float): Drilling depth for geothermal wells.
        Temperatur_Geothermie (float): Temperature of the geothermal source.
        spez_Bohrkosten (float): Specific drilling costs per meter. Default is 100.
        spez_Entzugsleistung (float): Specific extraction performance per meter. Default is 50.
        Vollbenutzungsstunden (float): Full utilization hours per year. Default is 2400.
        Abstand_Sonden (float): Distance between probes. Default is 10.
        min_Teillast (float): Minimum partial load. Default is 0.2.
        co2_factor_electricity (float): CO2 emission factor for electricity in tCO2/MWh. Default is 0.4.
        primärenergiefaktor (float): Primary energy factor. Default is 2.4.

    Methods:
        Geothermie(Last_L, VLT_L, COP_data, duration): Calculates the geothermal heat extraction and other performance metrics.
        calculate(VLT_L, COP_data, Strompreis, q, r, T, BEW, stundensatz, duration, general_results): Calculates the economic and environmental metrics for the geothermal heat pump.
        to_dict(): Converts the object attributes to a dictionary.
        from_dict(data): Creates an object from a dictionary of attributes.
    """
    def __init__(self, name, Fläche, Bohrtiefe, Temperatur_Geothermie, spez_Bohrkosten=100, spez_Entzugsleistung=50,
                 Vollbenutzungsstunden=2400, Abstand_Sonden=10, spezifische_Investitionskosten_WP=1000, min_Teillast=0.2):
        super().__init__(name, spezifische_Investitionskosten_WP=spezifische_Investitionskosten_WP)
        self.Fläche = Fläche
        self.Bohrtiefe = Bohrtiefe
        self.Temperatur_Geothermie = Temperatur_Geothermie
        self.spez_Bohrkosten = spez_Bohrkosten
        self.spez_Entzugsleistung = spez_Entzugsleistung
        self.Vollbenutzungsstunden = Vollbenutzungsstunden
        self.Abstand_Sonden = Abstand_Sonden
        self.min_Teillast = min_Teillast
        self.co2_factor_electricity = 0.4 # tCO2/MWh electricity
        self.primärenergiefaktor = 2.4

    def Geothermie(self, Last_L, VLT_L, COP_data, duration):
        """
        Calculates the geothermal heat extraction and other performance metrics.

        Args:
            Last_L (array-like): Load demand.
            VLT_L (array-like): Flow temperatures.
            COP_data (array-like): COP data for interpolation.
            duration (float): Time duration.

        Returns:
            tuple: Heat energy, electricity demand, heat output, electric power.
        """
        if self.Fläche == 0 or self.Bohrtiefe == 0:
            return 0, 0, np.zeros_like(Last_L), np.zeros_like(VLT_L)

        Anzahl_Sonden = (round(sqrt(self.Fläche) / self.Abstand_Sonden) + 1) ** 2

        Entzugsleistung_2400 = self.Bohrtiefe * self.spez_Entzugsleistung * Anzahl_Sonden / 1000
        # kW bei 2400 h, 22 Sonden, 50 W/m: 220 kW
        Entzugswärmemenge = Entzugsleistung_2400 * self.Vollbenutzungsstunden / 1000  # MWh
        self.Investitionskosten_Sonden = self.Bohrtiefe * self.spez_Bohrkosten * Anzahl_Sonden

        COP_L, VLT_WP = self.COP_WP(VLT_L, self.Temperatur_Geothermie, COP_data)

        # tatsächliche Anzahl der Betriebsstunden der Wärmepumpe hängt von der Wärmeleistung ab,
        # diese hängt über Entzugsleistung von der angenommenen Betriebsstundenzahl ab
        B_min = 1
        B_max = 8760
        tolerance = 0.5
        while B_max - B_min > tolerance:
            B = (B_min + B_max) / 2
            # Berechnen der Entzugsleistung
            Entzugsleistung = Entzugswärmemenge * 1000 / B  # kW
            # Berechnen der Wärmeleistung und elektrischen Leistung
            Wärmeleistung_L = Entzugsleistung / (1 - (1 / COP_L))
            el_Leistung_L = Wärmeleistung_L - Entzugsleistung

            # Berechnen der tatsächlichen Werte
            Wärmeleistung_tat_L = np.zeros_like(Last_L)
            el_Leistung_tat_L = np.zeros_like(Last_L)
            Entzugsleistung_tat_L = np.zeros_like(Last_L)

            # Fälle, in denen die Wärmepumpe betrieben werden kann
            betrieb_mask = Last_L >= Wärmeleistung_L * self.min_Teillast
            Wärmeleistung_tat_L[betrieb_mask] = np.minimum(Last_L[betrieb_mask], Wärmeleistung_L[betrieb_mask])
            el_Leistung_tat_L[betrieb_mask] = Wärmeleistung_tat_L[betrieb_mask] - (Entzugsleistung * np.ones_like(Last_L))[betrieb_mask]
            Entzugsleistung_tat_L[betrieb_mask] = Wärmeleistung_tat_L[betrieb_mask] - el_Leistung_tat_L[betrieb_mask]

            Entzugswärme = np.sum(Entzugsleistung_tat_L) / 1000
            Wärmemenge = np.sum(Wärmeleistung_tat_L) / 1000
            Strombedarf = np.sum(el_Leistung_tat_L) / 1000
            Betriebsstunden = np.count_nonzero(Wärmeleistung_tat_L)

            # Falls es keine Nutzung gibt, wird das Ergebnis 0
            if Betriebsstunden == 0:
                Wärmeleistung_tat_L = np.array([0])
                el_Leistung_tat_L = np.array([0])

            if Entzugswärme > Entzugswärmemenge:
                B_min = B
            else:
                B_max = B

        self.max_Wärmeleistung = max(Wärmeleistung_tat_L)
        JAZ = Wärmemenge / Strombedarf
        Wärmemenge, Strombedarf = Wärmemenge * duration, Strombedarf * duration
        
        return Wärmemenge, Strombedarf, Wärmeleistung_tat_L, el_Leistung_tat_L
    
    def calculate(self, VLT_L, COP_data, Strompreis, q, r, T, BEW, stundensatz, duration, general_results):
        """
        Calculates the economic and environmental metrics for the geothermal heat pump.

        Args:
            VLT_L (array-like): Flow temperatures.
            COP_data (array-like): COP data for interpolation.
            Strompreis (float): Price of electricity.
            q (float): Interest rate factor.
            r (float): Inflation rate factor.
            T (int): Consideration period in years.
            BEW (float): Discount rate.
            stundensatz (float): Hourly labor rate.
            duration (float): Time duration.
            general_results (dict): Dictionary containing general results and metrics.

        Returns:
            dict: Dictionary containing calculated metrics and results.
        """
        self.Wärmemenge_Geothermie, self.Strombedarf_Geothermie, self.Wärmeleistung_kW, self.el_Leistung_kW = self.Geothermie(general_results['Restlast_L'], VLT_L, COP_data, duration)

        self.spez_Investitionskosten_Erdsonden = self.Investitionskosten_Sonden / self.max_Wärmeleistung
        WGK_Geothermie = self.WGK(self.max_Wärmeleistung, self.Wärmemenge_Geothermie, self.Strombedarf_Geothermie, self.spez_Investitionskosten_Erdsonden, Strompreis, q, r, T, BEW, stundensatz)

        # CO2 emissions due to fuel usage
        self.co2_emissions = self.Strombedarf_Geothermie * self.co2_factor_electricity # tCO2
        # specific emissions heat
        self.spec_co2_total = self.co2_emissions / self.Wärmemenge_Geothermie if self.Wärmemenge_Geothermie > 0 else 0 # tCO2/MWh_heat

        self.primärenergie = self.Strombedarf_Geothermie * self.primärenergiefaktor

        results = {
            'Wärmemenge': self.Wärmemenge_Geothermie,
            'Wärmeleistung_L': self.Wärmeleistung_kW,
            'Strombedarf': self.Strombedarf_Geothermie,
            'el_Leistung_L': self.el_Leistung_kW,
            'WGK': WGK_Geothermie,
            'spec_co2_total': self.spec_co2_total,
            'primärenergie': self.primärenergie,
            'color': "darkorange"
        }

        return results

    def to_dict(self):
        """
        Converts the object attributes to a dictionary.

        Returns:
            dict: Dictionary containing object attributes.
        """
        return self.__dict__
    
    @staticmethod
    def from_dict(data):
        """
        Creates an object from a dictionary of attributes.

        Args:
            data (dict): Dictionary containing object attributes.

        Returns:
            Geothermal: Created object from the given dictionary.
        """
        obj = Geothermal.__new__(Geothermal)
        obj.__dict__.update(data)
        return obj

class CHP:
    """
    This class represents a Combined Heat and Power (CHP) system and provides methods to calculate various performance and economic metrics.

    Args:
        name (str): Name of the CHP system.
        th_Leistung_BHKW (float): Thermal power of the CHP system in kW.
        spez_Investitionskosten_GBHKW (float): Specific investment costs for gas CHP in €/kW. Default is 1500.
        spez_Investitionskosten_HBHKW (float): Specific investment costs for wood gas CHP in €/kW. Default is 1850.
        el_Wirkungsgrad (float): Electrical efficiency of the CHP system. Default is 0.33.
        KWK_Wirkungsgrad (float): Combined heat and power efficiency. Default is 0.9.
        min_Teillast (float): Minimum partial load. Default is 0.7.
        speicher_aktiv (bool): Flag indicating if the storage is active. Default is False.
        Speicher_Volumen_BHKW (float): Storage volume in m³. Default is 20.
        T_vorlauf (float): Flow temperature in °C. Default is 90.
        T_ruecklauf (float): Return temperature in °C. Default is 60.
        initial_fill (float): Initial fill level of the storage. Default is 0.0.
        min_fill (float): Minimum fill level of the storage. Default is 0.2.
        max_fill (float): Maximum fill level of the storage. Default is 0.8.
        spez_Investitionskosten_Speicher (float): Specific investment costs for storage in €/m³. Default is 750.
        BHKW_an (bool): Flag indicating if the CHP is on. Default is True.
        opt_BHKW_min (float): Minimum optimization value for CHP. Default is 0.
        opt_BHKW_max (float): Maximum optimization value for CHP. Default is 1000.
        opt_BHKW_Speicher_min (float): Minimum optimization value for CHP storage. Default is 0.
        opt_BHKW_Speicher_max (float): Maximum optimization value for CHP storage. Default is 100.

    Attributes:
        thermischer_Wirkungsgrad (float): Thermal efficiency of the CHP system.
        el_Leistung_Soll (float): Desired electrical power of the CHP system in kW.
        Nutzungsdauer (int): Usage duration in years.
        f_Inst (float): Installation factor.
        f_W_Insp (float): Inspection factor.
        Bedienaufwand (float): Operating effort.
        co2_factor_fuel (float): CO2 emission factor for fuel in tCO2/MWh.
        primärenergiefaktor (float): Primary energy factor.
        co2_factor_electricity (float): CO2 emission factor for electricity in tCO2/MWh.

    Methods:
        BHKW(Last_L, duration): Calculates the power and heat output of the CHP system without storage.
        storage(Last_L, duration): Calculates the power and heat output of the CHP system with storage.
        WGK(Wärmemenge, Strommenge, Brennstoffbedarf, Brennstoffkosten, Strompreis, q, r, T, BEW, stundensatz): Calculates the economic metrics for the CHP system.
        calculate(Gaspreis, Holzpreis, Strompreis, q, r, T, BEW, stundensatz, duration, general_results): Calculates the economic and environmental metrics for the CHP system.
        to_dict(): Converts the object attributes to a dictionary.
        from_dict(data): Creates an object from a dictionary of attributes.
    """
    def __init__(self, name, th_Leistung_BHKW, spez_Investitionskosten_GBHKW=1500, spez_Investitionskosten_HBHKW=1850, el_Wirkungsgrad=0.33, KWK_Wirkungsgrad=0.9, 
                 min_Teillast=0.7, speicher_aktiv=False, Speicher_Volumen_BHKW=20, T_vorlauf=90, T_ruecklauf=60, initial_fill=0.0, min_fill=0.2, max_fill=0.8, 
                 spez_Investitionskosten_Speicher=750, BHKW_an=True, opt_BHKW_min=0, opt_BHKW_max=1000, opt_BHKW_Speicher_min=0, opt_BHKW_Speicher_max=100):
        self.name = name
        self.th_Leistung_BHKW = th_Leistung_BHKW
        self.spez_Investitionskosten_GBHKW = spez_Investitionskosten_GBHKW
        self.spez_Investitionskosten_HBHKW = spez_Investitionskosten_HBHKW
        self.el_Wirkungsgrad = el_Wirkungsgrad
        self.KWK_Wirkungsgrad = KWK_Wirkungsgrad
        self.min_Teillast = min_Teillast
        self.speicher_aktiv = speicher_aktiv
        self.Speicher_Volumen_BHKW = Speicher_Volumen_BHKW
        self.T_vorlauf = T_vorlauf
        self.T_ruecklauf = T_ruecklauf
        self.initial_fill = initial_fill
        self.min_fill = min_fill
        self.max_fill = max_fill
        self.spez_Investitionskosten_Speicher = spez_Investitionskosten_Speicher
        self.BHKW_an = BHKW_an
        self.opt_BHKW_min = opt_BHKW_min
        self.opt_BHKW_max = opt_BHKW_max
        self.opt_BHKW_Speicher_min = opt_BHKW_Speicher_min
        self.opt_BHKW_Speicher_max = opt_BHKW_Speicher_max
        self.thermischer_Wirkungsgrad = self.KWK_Wirkungsgrad - self.el_Wirkungsgrad
        self.el_Leistung_Soll = self.th_Leistung_BHKW / self.thermischer_Wirkungsgrad * self.el_Wirkungsgrad
        self.Nutzungsdauer = 15
        self.f_Inst, self.f_W_Insp, self.Bedienaufwand = 6, 2, 0
        if self.name.startswith("BHKW"):
            self.co2_factor_fuel = 0.201 # tCO2/MWh gas
            self.primärenergiefaktor = 1.1 # Gas
        elif self.name.startswith("Holzgas-BHKW"):
            self.co2_factor_fuel = 0.036 # tCO2/MWh pellets
            self.primärenergiefaktor = 0.2 # Pellets
        self.co2_factor_electricity = 0.4 # tCO2/MWh electricity

    def BHKW(self, Last_L, duration):
        """
        Calculates the power and heat output of the CHP system without storage.

        Args:
            Last_L (array-like): Load demand.
            duration (float): Time duration.

        Returns:
            None
        """
        self.Wärmeleistung_kW = np.zeros_like(Last_L)
        self.el_Leistung_kW = np.zeros_like(Last_L)

        # Fälle, in denen das BHKW betrieben werden kann
        betrieb_mask = Last_L >= self.th_Leistung_BHKW * self.min_Teillast
        self.Wärmeleistung_kW[betrieb_mask] = np.minimum(Last_L[betrieb_mask], self.th_Leistung_BHKW)
        self.el_Leistung_kW[betrieb_mask] = self.Wärmeleistung_kW[betrieb_mask] / self.thermischer_Wirkungsgrad * self.el_Wirkungsgrad

        self.Wärmemenge_BHKW = np.sum(self.Wärmeleistung_kW / 1000) * duration
        self.Strommenge_BHKW = np.sum(self.el_Leistung_kW / 1000) * duration

        # Berechnen des Brennstoffbedarfs
        self.Brennstoffbedarf_BHKW = (self.Wärmemenge_BHKW + self.Strommenge_BHKW) / self.KWK_Wirkungsgrad

        # Anzahl Starts und Betriebsstunden pro Start berechnen
        starts = np.diff(betrieb_mask.astype(int)) > 0
        self.Anzahl_Starts = np.sum(starts)
        self.Betriebsstunden_gesamt = np.sum(betrieb_mask) * duration
        self.Betriebsstunden_pro_Start = self.Betriebsstunden_gesamt / self.Anzahl_Starts if self.Anzahl_Starts > 0 else 0

    def storage(self, Last_L, duration):
        """
        Calculates the power and heat output of the CHP system with storage.

        Args:
            Last_L (array-like): Load demand.
            duration (float): Time duration.

        Returns:
            None
        """
        # Speicherparameter
        speicher_kapazitaet = self.Speicher_Volumen_BHKW * 4186 * (self.T_vorlauf - self.T_ruecklauf) / 3600  # kWh
        speicher_fill = self.initial_fill * speicher_kapazitaet
        min_speicher_fill = self.min_fill * speicher_kapazitaet
        max_speicher_fill = self.max_fill * speicher_kapazitaet

        self.Wärmeleistung_kW = np.zeros_like(Last_L)
        self.Wärmeleistung_Speicher_kW = np.zeros_like(Last_L)
        self.el_Leistung_BHKW_kW = np.zeros_like(Last_L)
        self.speicher_fuellstand_BHKW = np.zeros_like(Last_L)

        for i in range(len(Last_L)):
            if self.BHKW_an:
                if speicher_fill >= max_speicher_fill:
                    self.BHKW_an = False
                else:
                    self.Wärmeleistung_kW[i] = self.th_Leistung_BHKW
                    if Last_L[i] < self.th_Leistung_BHKW:
                        self.Wärmeleistung_Speicher_kW[i] = Last_L[i] - self.th_Leistung_BHKW
                        speicher_fill += (self.th_Leistung_BHKW - Last_L[i]) * duration
                        speicher_fill = float(min(speicher_fill, speicher_kapazitaet))
                    else:
                        self.Wärmeleistung_Speicher_kW[i] = 0
            else:
                if speicher_fill <= min_speicher_fill:
                    self.BHKW_an = True
            
            if not self.BHKW_an:
                self.Wärmeleistung_kW[i] = 0
                self.Wärmeleistung_Speicher_kW[i] = Last_L[i]
                speicher_fill -= Last_L[i] * duration
                speicher_fill = float(max(speicher_fill, 0))

            self.el_Leistung_BHKW_kW[i] = self.Wärmeleistung_kW[i] / self.thermischer_Wirkungsgrad * self.el_Wirkungsgrad
            self.speicher_fuellstand_BHKW[i] = speicher_fill / speicher_kapazitaet * 100  # %

        self.Wärmemenge_BHKW_Speicher = np.sum(self.Wärmeleistung_kW / 1000) * duration
        self.Strommenge_BHKW_Speicher = np.sum(self.el_Leistung_BHKW_kW / 1000) * duration

        # Berechnen des Brennstoffbedarfs
        self.Brennstoffbedarf_BHKW_Speicher = (self.Wärmemenge_BHKW_Speicher + self.Strommenge_BHKW_Speicher) / self.KWK_Wirkungsgrad

        # Anzahl Starts und Betriebsstunden pro Start berechnen
        betrieb_mask = self.Wärmeleistung_kW > 0
        starts = np.diff(betrieb_mask.astype(int)) > 0
        self.Anzahl_Starts_Speicher = np.sum(starts)
        self.Betriebsstunden_gesamt_Speicher = np.sum(betrieb_mask) * duration
        self.Betriebsstunden_pro_Start_Speicher = self.Betriebsstunden_gesamt_Speicher / self.Anzahl_Starts_Speicher if self.Anzahl_Starts_Speicher > 0 else 0
    
    def WGK(self, Wärmemenge, Strommenge, Brennstoffbedarf, Brennstoffkosten, Strompreis, q, r, T, BEW, stundensatz):
        """
        Calculates the economic metrics for the CHP system.

        Args:
            Wärmemenge (float): Amount of heat generated.
            Strommenge (float): Amount of electricity generated.
            Brennstoffbedarf (float): Fuel consumption.
            Brennstoffkosten (float): Fuel costs.
            Strompreis (float): Electricity price.
            q (float): Factor for capital recovery.
            r (float): Factor for price escalation.
            T (int): Time period in years.
            BEW (float): BEW factor.
            stundensatz (float): Hourly rate.

        Returns:
            float: Weighted average cost of energy for the CHP system.
        """
        if Wärmemenge == 0:
            return 0
        # Holzvergaser-BHKW: 130 kW: 240.000 -> 1850 €/kW
        # (Erd-)Gas-BHKW: 100 kW: 150.000 € -> 1500 €/kW
        if self.name.startswith("BHKW"):
            spez_Investitionskosten_BHKW = self.spez_Investitionskosten_GBHKW  # €/kW
        elif self.name.startswith("Holzgas-BHKW"):
            spez_Investitionskosten_BHKW = self.spez_Investitionskosten_HBHKW  # €/kW

        self.Investitionskosten_BHKW = spez_Investitionskosten_BHKW * self.th_Leistung_BHKW
        self.Investitionskosten_Speicher = self.spez_Investitionskosten_Speicher * self.Speicher_Volumen_BHKW
        self.Investitionskosten = self.Investitionskosten_BHKW + self.Investitionskosten_Speicher

        self.Stromeinnahmen = Strommenge * Strompreis

        self.A_N = annuität(self.Investitionskosten, self.Nutzungsdauer, self.f_Inst, self.f_W_Insp, self.Bedienaufwand, q, r, T, Brennstoffbedarf, Brennstoffkosten, self.Stromeinnahmen, stundensatz)
        self.WGK_BHKW = self.A_N / Wärmemenge

    def calculate(self, Gaspreis, Holzpreis, Strompreis, q, r, T, BEW, stundensatz, duration, general_results):
        """
        Calculates the economic and environmental metrics for the CHP system.

        Args:
            Gaspreis (float): Gas price.
            Holzpreis (float): Wood price.
            Strompreis (float): Electricity price.
            q (float): Factor for capital recovery.
            r (float): Factor for price escalation.
            T (int): Time period in years.
            BEW (float): BEW factor.
            stundensatz (float): Hourly rate.
            duration (float): Time duration.
            general_results (dict): Dictionary containing general results.

        Returns:
            dict: Dictionary containing calculated results.
        """
        if self.speicher_aktiv:
            self.storage(general_results["Restlast_L"], duration)
            Wärmemenge = self.Wärmemenge_BHKW_Speicher
            Strommenge = self.Strommenge_BHKW_Speicher
            Brennstoffbedarf = self.Brennstoffbedarf_BHKW_Speicher
            Wärmeleistung_kW = self.Wärmeleistung_kW
            el_Leistung_BHKW = self.el_Leistung_BHKW_kW
            Anzahl_Starts = self.Anzahl_Starts_Speicher
            Betriebsstunden = self.Betriebsstunden_gesamt_Speicher
            Betriebsstunden_pro_Start = self.Betriebsstunden_pro_Start_Speicher
        else:
            self.BHKW(general_results["Restlast_L"], duration)
            Wärmemenge = self.Wärmemenge_BHKW
            Strommenge = self.Strommenge_BHKW
            Brennstoffbedarf = self.Brennstoffbedarf_BHKW
            Wärmeleistung_kW = self.Wärmeleistung_kW
            el_Leistung_BHKW = self.el_Leistung_kW
            Anzahl_Starts = self.Anzahl_Starts
            Betriebsstunden = self.Betriebsstunden_gesamt
            Betriebsstunden_pro_Start = self.Betriebsstunden_pro_Start

        if self.name.startswith("BHKW"):
            self.Brennstoffpreis = Gaspreis
        elif self.name.startswith("Holzgas-BHKW"):
            self.Brennstoffpreis = Holzpreis

        self.WGK(Wärmemenge, Strommenge, Brennstoffbedarf, self.Brennstoffpreis, Strompreis, q, r, T, BEW, stundensatz)

        # CO2 emissions due to fuel usage
        self.co2_emissions = Brennstoffbedarf * self.co2_factor_fuel # tCO2
        # CO2 savings due to electricity generation
        self.co2_savings = Strommenge * self.co2_factor_electricity # tCO2
        # total co2
        self.co2_total = self.co2_emissions - self.co2_savings # tCO2
        # specific emissions heat
        self.spec_co2_total = self.co2_total / Wärmemenge if Wärmemenge > 0 else 0 # tCO2/MWh_heat

        self.primärenergie = Brennstoffbedarf * self.primärenergiefaktor

        results = {
            'Wärmemenge': Wärmemenge,
            'Wärmeleistung_L': Wärmeleistung_kW,
            'Brennstoffbedarf': Brennstoffbedarf,
            'WGK': self.WGK_BHKW,
            'Strommenge': Strommenge,
            'el_Leistung_L': el_Leistung_BHKW,
            'Anzahl_Starts': Anzahl_Starts,
            'Betriebsstunden': Betriebsstunden,
            'Betriebsstunden_pro_Start': Betriebsstunden_pro_Start,
            'spec_co2_total': self.spec_co2_total,
            'primärenergie': self.primärenergie,
            'color': "yellow"
        }

        if self.speicher_aktiv:
            results['Wärmeleistung_Speicher_L'] = self.Wärmeleistung_Speicher_kW

        return results

    def to_dict(self):
        """
        Converts the object attributes to a dictionary.

        Returns:
            dict: Dictionary containing object attributes.
        """
        return self.__dict__

    @staticmethod
    def from_dict(data):
        """
        Creates an object from a dictionary of attributes.

        Args:
            data (dict): Dictionary containing object attributes.

        Returns:
            CHP: A new CHP object with attributes from the dictionary.
        """
        obj = CHP.__new__(CHP)
        obj.__dict__.update(data)
        return obj

class BiomassBoiler:
    """
    A class representing a biomass boiler system.

    Attributes:
        name (str): Name of the biomass boiler.
        P_BMK (float): Boiler power in kW.
        Größe_Holzlager (float): Size of the wood storage in cubic meters.
        spez_Investitionskosten (float): Specific investment costs for the boiler in €/kW.
        spez_Investitionskosten_Holzlager (float): Specific investment costs for the wood storage in €/m³.
        Nutzungsgrad_BMK (float): Efficiency of the biomass boiler.
        min_Teillast (float): Minimum part-load operation as a fraction of the nominal load.
        speicher_aktiv (bool): Indicates if a storage system is active.
        Speicher_Volumen (float): Volume of the thermal storage in cubic meters.
        T_vorlauf (float): Supply temperature in °C.
        T_ruecklauf (float): Return temperature in °C.
        initial_fill (float): Initial fill level of the storage as a fraction of the total volume.
        min_fill (float): Minimum fill level of the storage as a fraction of the total volume.
        max_fill (float): Maximum fill level of the storage as a fraction of the total volume.
        spez_Investitionskosten_Speicher (float): Specific investment costs for the thermal storage in €/m³.
        BMK_an (bool): Indicates if the boiler is on.
        opt_BMK_min (float): Minimum boiler capacity for optimization.
        opt_BMK_max (float): Maximum boiler capacity for optimization.
        opt_Speicher_min (float): Minimum storage capacity for optimization.
        opt_Speicher_max (float): Maximum storage capacity for optimization.
        Nutzungsdauer (int): Lifespan of the biomass boiler in years.
        f_Inst (float): Installation factor.
        f_W_Insp (float): Inspection factor.
        Bedienaufwand (float): Operational effort.
        co2_factor_fuel (float): CO2 factor for the fuel in tCO2/MWh.
        primärenergiefaktor (float): Primary energy factor for the fuel.
    """
    
    def __init__(self, name, P_BMK, Größe_Holzlager=40, spez_Investitionskosten=200, spez_Investitionskosten_Holzlager=400, Nutzungsgrad_BMK=0.8, min_Teillast=0.3,
                 speicher_aktiv=False, Speicher_Volumen=20, T_vorlauf=90, T_ruecklauf=60, initial_fill=0.0, min_fill=0.2, max_fill=0.8, 
                 spez_Investitionskosten_Speicher=750, BMK_an=True, opt_BMK_min=0, opt_BMK_max=1000, opt_Speicher_min=0, opt_Speicher_max=100):
        self.name = name
        self.P_BMK = P_BMK
        self.Größe_Holzlager = Größe_Holzlager
        self.spez_Investitionskosten = spez_Investitionskosten
        self.spez_Investitionskosten_Holzlager = spez_Investitionskosten_Holzlager
        self.Nutzungsgrad_BMK = Nutzungsgrad_BMK
        self.min_Teillast = min_Teillast
        self.speicher_aktiv = speicher_aktiv
        self.Speicher_Volumen = Speicher_Volumen
        self.T_vorlauf = T_vorlauf
        self.T_ruecklauf = T_ruecklauf
        self.initial_fill = initial_fill
        self.min_fill = min_fill
        self.max_fill = max_fill
        self.spez_Investitionskosten_Speicher = spez_Investitionskosten_Speicher
        self.BMK_an = BMK_an
        self.opt_BMK_min = opt_BMK_min
        self.opt_BMK_max = opt_BMK_max
        self.opt_Speicher_min = opt_Speicher_min
        self.opt_Speicher_max = opt_Speicher_max
        self.Nutzungsdauer = 15
        self.f_Inst, self.f_W_Insp, self.Bedienaufwand = 3, 3, 0
        self.co2_factor_fuel = 0.036 # tCO2/MWh pellets
        self.primärenergiefaktor = 0.2 # Pellets

    def Biomassekessel(self, Last_L, duration):
        """
        Simulates the operation of the biomass boiler.

        Args:
            Last_L (array): Load profile of the system in kW.
            duration (float): Duration of each time step in hours.

        Returns:
            None
        """
        self.Wärmeleistung_kW = np.zeros_like(Last_L)

        # Cases where the biomass boiler can operate
        betrieb_mask = Last_L >= self.P_BMK * self.min_Teillast
        self.Wärmeleistung_kW[betrieb_mask] = np.minimum(Last_L[betrieb_mask], self.P_BMK)

        self.Wärmemenge_BMK = np.sum(self.Wärmeleistung_kW / 1000) * duration
        self.Brennstoffbedarf_BMK = self.Wärmemenge_BMK / self.Nutzungsgrad_BMK

        # Calculate number of starts and operating hours per start
        starts = np.diff(betrieb_mask.astype(int)) > 0
        self.Anzahl_Starts = np.sum(starts)
        self.Betriebsstunden_gesamt = np.sum(betrieb_mask) * duration
        self.Betriebsstunden_pro_Start = self.Betriebsstunden_gesamt / self.Anzahl_Starts if self.Anzahl_Starts > 0 else 0

    def storage(self, Last_L, duration):
        """
        Simulates the operation of the storage system.

        Args:
            Last_L (array): Load profile of the system in kW.
            duration (float): Duration of each time step in hours.

        Returns:
            None
        """
        # Storage parameters
        speicher_kapazitaet = self.Speicher_Volumen * 4186 * (self.T_vorlauf - self.T_ruecklauf) / 3600  # kWh
        speicher_fill = self.initial_fill * speicher_kapazitaet
        min_speicher_fill = self.min_fill * speicher_kapazitaet
        max_speicher_fill = self.max_fill * speicher_kapazitaet

        self.Wärmeleistung_kW = np.zeros_like(Last_L)
        self.Wärmeleistung_Speicher_kW = np.zeros_like(Last_L)
        self.speicher_fuellstand = np.zeros_like(Last_L)

        for i in range(len(Last_L)):
            if self.BMK_an:
                if speicher_fill >= max_speicher_fill:
                    self.BMK_an = False
                else:
                    self.Wärmeleistung_kW[i] = self.P_BMK
                    if Last_L[i] < self.P_BMK:
                        self.Wärmeleistung_Speicher_kW[i] = Last_L[i] - self.P_BMK
                        speicher_fill += (self.P_BMK - Last_L[i]) * duration
                        speicher_fill = float(min(speicher_fill, speicher_kapazitaet))
                    else:
                        self.Wärmeleistung_Speicher_kW[i] = 0
            else:
                if speicher_fill <= min_speicher_fill:
                    self.BMK_an = True
            
            if not self.BMK_an:
                self.Wärmeleistung_kW[i] = 0
                self.Wärmeleistung_Speicher_kW[i] = Last_L[i]
                speicher_fill -= Last_L[i] * duration
                speicher_fill = float(max(speicher_fill, 0))

            self.speicher_fuellstand[i] = speicher_fill / speicher_kapazitaet * 100  # %

        self.Wärmemenge_Biomassekessel_Speicher = np.sum(self.Wärmeleistung_kW / 1000) * duration

        # Calculate fuel consumption
        self.Brennstoffbedarf_BMK_Speicher = self.Wärmemenge_Biomassekessel_Speicher / self.Nutzungsgrad_BMK

        # Calculate number of starts and operating hours per start
        betrieb_mask = self.Wärmeleistung_kW > 0
        starts = np.diff(betrieb_mask.astype(int)) > 0
        self.Anzahl_Starts_Speicher = np.sum(starts)
        self.Betriebsstunden_gesamt_Speicher = np.sum(betrieb_mask) * duration
        self.Betriebsstunden_pro_Start_Speicher = self.Betriebsstunden_gesamt_Speicher / self.Anzahl_Starts_Speicher if self.Anzahl_Starts_Speicher > 0 else 0

    def WGK(self, Wärmemenge, Brennstoffbedarf, Brennstoffkosten, q, r, T, BEW, stundensatz):
        """
        Calculates the weighted average cost of heat generation.

        Args:
            Wärmemenge (float): Amount of heat generated.
            Brennstoffbedarf (float): Fuel consumption.
            Brennstoffkosten (float): Fuel costs.
            q (float): Factor for capital recovery.
            r (float): Factor for price escalation.
            T (int): Time period in years.
            BEW (float): Factor for operational costs.
            stundensatz (float): Hourly rate for labor.

        Returns:
            float: Weighted average cost of heat generation.
        """
        if Wärmemenge == 0:
            return 0
        
        self.Investitionskosten_Kessel = self.spez_Investitionskosten * self.P_BMK
        self.Investitionskosten_Holzlager = self.spez_Investitionskosten_Holzlager * self.Größe_Holzlager
        self.Investitionskosten_Speicher = self.spez_Investitionskosten_Speicher * self.Speicher_Volumen
        self.Investitionskosten = self.Investitionskosten_Kessel + self.Investitionskosten_Holzlager + self.Investitionskosten_Speicher

        self.A_N = annuität(self.Investitionskosten, self.Nutzungsdauer, self.f_Inst, self.f_W_Insp, self.Bedienaufwand, q, r, T, Brennstoffbedarf,
                            Brennstoffkosten, stundensatz=stundensatz)
        
        self.WGK_BMK = self.A_N / Wärmemenge

    def calculate(self, Holzpreis, q, r, T, BEW, stundensatz, duration, general_results):
        """
        Calculates the performance and cost of the biomass boiler system.

        Args:
            Holzpreis (float): Cost of wood fuel.
            q (float): Factor for capital recovery.
            r (float): Factor for price escalation.
            T (int): Time period in years.
            BEW (float): Factor for operational costs.
            stundensatz (float): Hourly rate for labor.
            duration (float): Duration of each time step in hours.
            general_results (dict): General results dictionary containing rest load.

        Returns:
            dict: Dictionary containing the results of the calculation.
        """
        if self.speicher_aktiv:
            self.storage(general_results["Restlast_L"], duration)
            Wärmemenge = self.Wärmemenge_Biomassekessel_Speicher
            Brennstoffbedarf = self.Brennstoffbedarf_BMK_Speicher
            Wärmeleistung_kW = self.Wärmeleistung_kW
            Anzahl_Starts = self.Anzahl_Starts_Speicher
            Betriebsstunden = self.Betriebsstunden_gesamt_Speicher
            Betriebsstunden_pro_Start = self.Betriebsstunden_pro_Start_Speicher
        else:
            self.Biomassekessel(general_results["Restlast_L"], duration)
            Wärmemenge = self.Wärmemenge_BMK
            Brennstoffbedarf = self.Brennstoffbedarf_BMK
            Wärmeleistung_kW = self.Wärmeleistung_kW
            Anzahl_Starts = self.Anzahl_Starts
            Betriebsstunden = self.Betriebsstunden_gesamt
            Betriebsstunden_pro_Start = self.Betriebsstunden_pro_Start

        self.WGK(Wärmemenge, Brennstoffbedarf, Holzpreis, q, r, T, BEW, stundensatz)

        # CO2 emissions due to fuel usage
        self.co2_emissions = Brennstoffbedarf * self.co2_factor_fuel # tCO2
        # specific emissions heat
        self.spec_co2_total = self.co2_emissions / Wärmemenge if Wärmemenge > 0 else 0 # tCO2/MWh_heat

        self.primärenergie = Brennstoffbedarf * self.primärenergiefaktor
        
        results = {
            'Wärmemenge': Wärmemenge,
            'Wärmeleistung_L': Wärmeleistung_kW,
            'Brennstoffbedarf': Brennstoffbedarf,
            'WGK': self.WGK_BMK,
            'Anzahl_Starts': Anzahl_Starts,
            'Betriebsstunden': Betriebsstunden,
            'Betriebsstunden_pro_Start': Betriebsstunden_pro_Start,
            'spec_co2_total': self.spec_co2_total,
            'primärenergie': self.primärenergie,
            'color': "green"
        }

        if self.speicher_aktiv:
            results['Wärmeleistung_Speicher_L'] = self.Wärmeleistung_Speicher_kW

        return results

    def to_dict(self):
        """
        Converts the BiomassBoiler object to a dictionary.

        Returns:
            dict: Dictionary representation of the BiomassBoiler object.
        """
        return self.__dict__

    @staticmethod
    def from_dict(data):
        """
        Creates a BiomassBoiler object from a dictionary.

        Args:
            data (dict): Dictionary containing the attributes of a BiomassBoiler object.

        Returns:
            BiomassBoiler: A new BiomassBoiler object with attributes from the dictionary.
        """
        obj = BiomassBoiler.__new__(BiomassBoiler)
        obj.__dict__.update(data)
        return obj

class GasBoiler:
    """
    A class representing a gas boiler system.

    Attributes:
        name (str): Name of the gas boiler.
        spez_Investitionskosten (float): Specific investment costs for the boiler in €/kW.
        Nutzungsgrad (float): Efficiency of the gas boiler.
        Faktor_Dimensionierung (float): Dimensioning factor.
        Nutzungsdauer (int): Lifespan of the gas boiler in years.
        f_Inst (float): Installation factor.
        f_W_Insp (float): Inspection factor.
        Bedienaufwand (float): Operational effort.
        co2_factor_fuel (float): CO2 factor for the fuel in tCO2/MWh.
        primärenergiefaktor (float): Primary energy factor for the fuel.
    """

    def __init__(self, name, spez_Investitionskosten=30, Nutzungsgrad=0.9, Faktor_Dimensionierung=1):
        """
        Initializes the GasBoiler class.

        Args:
            name (str): Name of the gas boiler.
            spez_Investitionskosten (float, optional): Specific investment costs for the boiler in €/kW. Defaults to 30.
            Nutzungsgrad (float, optional): Efficiency of the gas boiler. Defaults to 0.9.
            Faktor_Dimensionierung (float, optional): Dimensioning factor. Defaults to 1.
        """
        self.name = name
        self.spez_Investitionskosten = spez_Investitionskosten
        self.Nutzungsgrad = Nutzungsgrad
        self.Faktor_Dimensionierung = Faktor_Dimensionierung
        self.Nutzungsdauer = 20
        self.f_Inst, self.f_W_Insp, self.Bedienaufwand = 1, 2, 0
        self.co2_factor_fuel = 0.201  # tCO2/MWh gas
        self.primärenergiefaktor = 1.1

    def Gaskessel(self, Last_L, duration):
        """
        Simulates the operation of the gas boiler.

        Args:
            Last_L (array): Load profile of the system in kW.
            duration (float): Duration of each time step in hours.

        Returns:
            None
        """
        self.Wärmeleistung_kW = np.maximum(Last_L, 0)
        self.Wärmemenge_Gaskessel = np.sum(self.Wärmeleistung_kW / 1000) * duration
        self.Gasbedarf = self.Wärmemenge_Gaskessel / self.Nutzungsgrad
        self.P_max = max(Last_L) * self.Faktor_Dimensionierung

    def WGK(self, Brennstoffkosten, q, r, T, BEW, stundensatz):
        """
        Calculates the weighted average cost of heat generation.

        Args:
            Brennstoffkosten (float): Fuel costs.
            q (float): Factor for capital recovery.
            r (float): Factor for price escalation.
            T (int): Time period in years.
            BEW (float): Factor for operational costs.
            stundensatz (float): Hourly rate for labor.

        Returns:
            float: Weighted average cost of heat generation.
        """
        if self.Wärmemenge_Gaskessel == 0:
            return 0
        
        self.Investitionskosten = self.spez_Investitionskosten * self.P_max

        self.A_N = annuität(self.Investitionskosten, self.Nutzungsdauer, self.f_Inst, self.f_W_Insp, self.Bedienaufwand, q, r, T,
                            self.Gasbedarf, Brennstoffkosten, stundensatz=stundensatz)
        self.WGK_GK = self.A_N / self.Wärmemenge_Gaskessel

    def calculate(self, Gaspreis, q, r, T, BEW, stundensatz, duration, Last_L, general_results):
        """
        Calculates the performance and cost of the gas boiler system.

        Args:
            Gaspreis (float): Cost of gas.
            q (float): Factor for capital recovery.
            r (float): Factor for price escalation.
            T (int): Time period in years.
            BEW (float): Factor for operational costs.
            stundensatz (float): Hourly rate for labor.
            duration (float): Duration of each time step in hours.
            Last_L (array): Load profile of the system in kW.
            general_results (dict): General results dictionary containing rest load.

        Returns:
            dict: Dictionary containing the results of the calculation.
        """
        self.Gaskessel(general_results['Restlast_L'], duration)
        self.WGK(Gaspreis, q, r, T, BEW, stundensatz)

        # CO2 emissions due to fuel usage
        self.co2_emissions = self.Gasbedarf * self.co2_factor_fuel  # tCO2
        # specific emissions heat
        self.spec_co2_total = self.co2_emissions / self.Wärmemenge_Gaskessel if self.Wärmemenge_Gaskessel > 0 else 0  # tCO2/MWh_heat

        self.primärenergie = self.Gasbedarf * self.primärenergiefaktor

        results = {
            'Wärmemenge': self.Wärmemenge_Gaskessel,
            'Wärmeleistung_L': self.Wärmeleistung_kW,
            'Brennstoffbedarf': self.Gasbedarf,
            'WGK': self.WGK_GK,
            'spec_co2_total': self.spec_co2_total,
            'primärenergie': self.primärenergie,
            "color": "saddlebrown"
        }

        return results
    
    def to_dict(self):
        """
        Converts the GasBoiler object to a dictionary.

        Returns:
            dict: Dictionary representation of the GasBoiler object.
        """
        return self.__dict__

    @staticmethod
    def from_dict(data):
        """
        Creates a GasBoiler object from a dictionary.

        Args:
            data (dict): Dictionary containing the attributes of a GasBoiler object.

        Returns:
            GasBoiler: A new GasBoiler object with attributes from the dictionary.
        """
        obj = GasBoiler.__new__(GasBoiler)
        obj.__dict__.update(data)
        return obj

class SolarThermal:
    """
    A class representing a solar thermal system.

    Attributes:
        name (str): Name of the solar thermal system.
        bruttofläche_STA (float): Gross area of the solar thermal system in square meters.
        vs (float): Volume of the storage system in cubic meters.
        Typ (str): Type of solar collector, e.g., "Flachkollektor" or "Vakuumröhrenkollektor".
        kosten_speicher_spez (float): Specific costs for the storage system in €/m^3.
        kosten_fk_spez (float): Specific costs for flat plate collectors in €/m^2.
        kosten_vrk_spez (float): Specific costs for vacuum tube collectors in €/m^2.
        Tsmax (float): Maximum storage temperature in degrees Celsius.
        Longitude (float): Longitude of the installation site.
        STD_Longitude (float): Standard longitude for the time zone.
        Latitude (float): Latitude of the installation site.
        East_West_collector_azimuth_angle (float): Azimuth angle of the collector in degrees.
        Collector_tilt_angle (float): Tilt angle of the collector in degrees.
        Tm_rl (float): Mean return temperature in degrees Celsius.
        Qsa (float): Initial heat output.
        Vorwärmung_K (float): Preheating in Kelvin.
        DT_WT_Solar_K (float): Temperature difference for the solar heat exchanger in Kelvin.
        DT_WT_Netz_K (float): Temperature difference for the network heat exchanger in Kelvin.
        opt_volume_min (float): Minimum optimization volume in cubic meters.
        opt_volume_max (float): Maximum optimization volume in cubic meters.
        opt_area_min (float): Minimum optimization area in square meters.
        opt_area_max (float): Maximum optimization area in square meters.
        kosten_pro_typ (dict): Dictionary containing the specific costs for different types of collectors.
        Kosten_STA_spez (float): Specific costs for the solar thermal system.
        Nutzungsdauer (int): Service life of the solar thermal system in years.
        f_Inst (float): Installation factor.
        f_W_Insp (float): Inspection factor.
        Bedienaufwand (float): Operational effort.
        Anteil_Förderung_BEW (float): Subsidy rate for the renewable energy law.
        Betriebskostenförderung_BEW (float): Operational cost subsidy for the renewable energy law in €/MWh.
        co2_factor_solar (float): CO2 factor for solar energy in tCO2/MWh.
        primärenergiefaktor (float): Primary energy factor for solar energy.
    """

    def __init__(self, name, bruttofläche_STA, vs, Typ, kosten_speicher_spez=750, kosten_fk_spez=430, kosten_vrk_spez=590, Tsmax=90, Longitude=-14.4222, 
                 STD_Longitude=-15, Latitude=51.1676, East_West_collector_azimuth_angle=0, Collector_tilt_angle=36, Tm_rl=60, Qsa=0, Vorwärmung_K=8, 
                 DT_WT_Solar_K=5, DT_WT_Netz_K=5, opt_volume_min=0, opt_volume_max=200, opt_area_min=0, opt_area_max=2000):
        """
        Initializes the SolarThermal class.

        Args:
            name (str): Name of the solar thermal system.
            bruttofläche_STA (float): Gross area of the solar thermal system in square meters.
            vs (float): Volume of the storage system in cubic meters.
            Typ (str): Type of solar collector, e.g., "Flachkollektor" or "Vakuumröhrenkollektor".
            kosten_speicher_spez (float, optional): Specific costs for the storage system in €/m^3. Defaults to 750.
            kosten_fk_spez (float, optional): Specific costs for flat plate collectors in €/m^2. Defaults to 430.
            kosten_vrk_spez (float, optional): Specific costs for vacuum tube collectors in €/m^2. Defaults to 590.
            Tsmax (float, optional): Maximum storage temperature in degrees Celsius. Defaults to 90.
            Longitude (float, optional): Longitude of the installation site. Defaults to -14.4222.
            STD_Longitude (float, optional): Standard longitude for the time zone. Defaults to -15.
            Latitude (float, optional): Latitude of the installation site. Defaults to 51.1676.
            East_West_collector_azimuth_angle (float, optional): Azimuth angle of the collector in degrees. Defaults to 0.
            Collector_tilt_angle (float, optional): Tilt angle of the collector in degrees. Defaults to 36.
            Tm_rl (float, optional): Mean return temperature in degrees Celsius. Defaults to 60.
            Qsa (float, optional): Initial heat output. Defaults to 0.
            Vorwärmung_K (float, optional): Preheating in Kelvin. Defaults to 8.
            DT_WT_Solar_K (float, optional): Temperature difference for the solar heat exchanger in Kelvin. Defaults to 5.
            DT_WT_Netz_K (float, optional): Temperature difference for the network heat exchanger in Kelvin. Defaults to 5.
            opt_volume_min (float, optional): Minimum optimization volume in cubic meters. Defaults to 0.
            opt_volume_max (float, optional): Maximum optimization volume in cubic meters. Defaults to 200.
            opt_area_min (float, optional): Minimum optimization area in square meters. Defaults to 0.
            opt_area_max (float, optional): Maximum optimization area in square meters. Defaults to 2000.
        """
        self.name = name
        self.bruttofläche_STA = bruttofläche_STA
        self.vs = vs
        self.Typ = Typ
        self.kosten_speicher_spez = kosten_speicher_spez
        self.kosten_fk_spez = kosten_fk_spez
        self.kosten_vrk_spez = kosten_vrk_spez
        self.Tsmax = Tsmax
        self.Longitude = Longitude
        self.STD_Longitude = STD_Longitude
        self.Latitude = Latitude
        self.East_West_collector_azimuth_angle = East_West_collector_azimuth_angle
        self.Collector_tilt_angle = Collector_tilt_angle
        self.Tm_rl = Tm_rl
        self.Qsa = Qsa
        self.Vorwärmung_K = Vorwärmung_K
        self.DT_WT_Solar_K = DT_WT_Solar_K
        self.DT_WT_Netz_K = DT_WT_Netz_K
        self.opt_volume_min = opt_volume_min
        self.opt_volume_max = opt_volume_max
        self.opt_area_min = opt_area_min
        self.opt_area_max = opt_area_max

        self.kosten_pro_typ = {
            # Viessmann Flachkollektor Vitosol 200-FM, 2,56 m²: 697,9 € (brutto); 586,5 € (netto) -> 229 €/m²
            # + 200 €/m² Installation/Zubehör
            "Flachkollektor": self.kosten_fk_spez,
            # Ritter Vakuumröhrenkollektor CPC XL1921 (4,99m²): 2299 € (brutto); 1932 € (Netto) -> 387 €/m²
            # + 200 €/m² Installation/Zubehör
            "Vakuumröhrenkollektor": self.kosten_vrk_spez
        }

        self.Kosten_STA_spez = self.kosten_pro_typ[self.Typ]  # €/m^2
        self.Nutzungsdauer = 20  # Jahre
        self.f_Inst, self.f_W_Insp, self.Bedienaufwand = 0.5, 1, 0
        self.Anteil_Förderung_BEW = 0.4
        self.Betriebskostenförderung_BEW = 10  # €/MWh 10 Jahre
        self.co2_factor_solar = 0.0  # tCO2/MWh heat is 0 ?
        self.primärenergiefaktor = 0.0

    def calc_WGK(self, q, r, T, BEW, stundensatz):
        """
        Calculates the weighted average cost of heat generation (WGK).

        Args:
            q (float): Factor for capital recovery.
            r (float): Factor for price escalation.
            T (int): Time period in years.
            BEW (str): Subsidy eligibility ("Ja" or "Nein").
            stundensatz (float): Hourly rate for labor.

        Returns:
            float: Weighted average cost of heat generation.
        """
        if self.Wärmemenge_Solarthermie == 0:
            return 0

        self.Investitionskosten_Speicher = self.vs * self.kosten_speicher_spez
        self.Investitionskosten_STA = self.bruttofläche_STA * self.Kosten_STA_spez
        self.Investitionskosten = self.Investitionskosten_Speicher + self.Investitionskosten_STA

        self.A_N = annuität(self.Investitionskosten, self.Nutzungsdauer, self.f_Inst, self.f_W_Insp, self.Bedienaufwand, q, r, T, stundensatz=stundensatz)
        self.WGK = self.A_N / self.Wärmemenge_Solarthermie

        self.Eigenanteil = 1 - self.Anteil_Förderung_BEW
        self.Investitionskosten_Gesamt_BEW = self.Investitionskosten * self.Eigenanteil
        self.Annuität_BEW = annuität(self.Investitionskosten_Gesamt_BEW, self.Nutzungsdauer, self.f_Inst, self.f_W_Insp, self.Bedienaufwand, q, r, T, stundensatz=stundensatz)
        self.WGK_BEW = self.Annuität_BEW / self.Wärmemenge_Solarthermie

        self.WGK_BEW_BKF = self.WGK_BEW - self.Betriebskostenförderung_BEW

        if BEW == "Nein":
            return self.WGK
        elif BEW == "Ja":
            return self.WGK_BEW_BKF
        
    def calculate(self, VLT_L, RLT_L, TRY, time_steps, calc1, calc2, q, r, T, BEW, stundensatz, duration, general_results):
        """
        Calculates the performance and cost of the solar thermal system.

        Args:
            VLT_L (array): Forward temperature profile in degrees Celsius.
            RLT_L (array): Return temperature profile in degrees Celsius.
            TRY (array): Test Reference Year data.
            time_steps (array): Array of time steps.
            calc1 (float): Calculation parameter 1.
            calc2 (float): Calculation parameter 2.
            q (float): Factor for capital recovery.
            r (float): Factor for price escalation.
            T (int): Time period in years.
            BEW (str): Subsidy eligibility ("Ja" or "Nein").
            stundensatz (float): Hourly rate for labor.
            duration (float): Duration of each time step in hours.
            general_results (dict): General results dictionary containing rest load.

        Returns:
            dict: Dictionary containing the results of the calculation.
        """
        # Berechnung der Solarthermieanlage
        self.Wärmemenge_Solarthermie, self.Wärmeleistung_kW, self.Speicherladung_Solarthermie, self.Speicherfüllstand_Solarthermie = Berechnung_STA(self.bruttofläche_STA, 
                                                                                                        self.vs, self.Typ, general_results['Restlast_L'], VLT_L, RLT_L, 
                                                                                                        TRY, time_steps, calc1, calc2, duration, self.Tsmax, self.Longitude, self.STD_Longitude, 
                                                                                                        self.Latitude, self.East_West_collector_azimuth_angle, self.Collector_tilt_angle, self.Tm_rl, 
                                                                                                        self.Qsa, self.Vorwärmung_K, self.DT_WT_Solar_K, self.DT_WT_Netz_K)
        # Berechnung der Wärmegestehungskosten
        self.WGK_Solarthermie = self.calc_WGK(q, r, T, BEW, stundensatz)

        # Berechnung der Emissionen
        self.co2_emissions = self.Wärmemenge_Solarthermie * self.co2_factor_solar  # tCO2
        # specific emissions heat
        self.spec_co2_total = self.co2_emissions / self.Wärmemenge_Solarthermie if self.Wärmemenge_Solarthermie > 0 else 0  # tCO2/MWh_heat

        self.primärenergie_Solarthermie = self.Wärmemenge_Solarthermie * self.primärenergiefaktor

        results = { 
            'Wärmemenge': self.Wärmemenge_Solarthermie,
            'Wärmeleistung_L': self.Wärmeleistung_kW,
            'WGK': self.WGK_Solarthermie,
            'spec_co2_total': self.spec_co2_total,
            'primärenergie': self.primärenergie_Solarthermie,
            'Speicherladung_L': self.Speicherladung_Solarthermie,
            'Speicherfüllstand_L': self.Speicherfüllstand_Solarthermie,
            'color': "red"
        }

        return results

    def to_dict(self):
        """
        Converts the SolarThermal object to a dictionary.

        Returns:
            dict: Dictionary representation of the SolarThermal object.
        """
        return self.__dict__

    @staticmethod
    def from_dict(data):
        """
        Creates a SolarThermal object from a dictionary.

        Args:
            data (dict): Dictionary containing the attributes of a SolarThermal object.

        Returns:
            SolarThermal: A new SolarThermal object with attributes from the dictionary.
        """
        obj = SolarThermal.__new__(SolarThermal)
        obj.__dict__.update(data)
        return obj

def calculate_factors(Kapitalzins, Preissteigerungsrate, Betrachtungszeitraum):
    """
    Calculate economic factors for energy generation mix optimization.

    Args:
        Kapitalzins (float): Capital interest rate as a percentage.
        Preissteigerungsrate (float): Inflation rate as a percentage.
        Betrachtungszeitraum (int): Consideration period in years.

    Returns:
        tuple: Calculated factors q (interest rate factor), r (inflation rate factor), and T (consideration period).
    """
    q = 1 + Kapitalzins / 100
    r = 1 + Preissteigerungsrate / 100
    T = Betrachtungszeitraum
    return q, r, T

def Berechnung_Erzeugermix(tech_order, initial_data, start, end, TRY, COP_data, Gaspreis, Strompreis, Holzpreis, BEW, variables=[], variables_order=[], kapitalzins=5, preissteigerungsrate=3, betrachtungszeitraum=20, stundensatz=45):
    """
    Calculate the optimal energy generation mix for a given set of technologies and parameters.

    Args:
        tech_order (list): List of technology objects to be considered.
        initial_data (tuple): Initial data including time steps, load profile, flow temperature, and return temperature.
        start (int): Start time step for the calculation.
        end (int): End time step for the calculation.
        TRY (object): Test Reference Year data for temperature and solar radiation.
        COP_data (object): Coefficient of Performance data for heat pumps.
        Gaspreis (float): Gas price in €/kWh.
        Strompreis (float): Electricity price in €/kWh.
        Holzpreis (float): Biomass price in €/kWh.
        BEW (float): Specific CO2 emissions for electricity in kg CO2/kWh.
        variables (list, optional): List of variable values for optimization. Defaults to [].
        variables_order (list, optional): List of variable names for optimization. Defaults to [].
        kapitalzins (int, optional): Capital interest rate in percentage. Defaults to 5.
        preissteigerungsrate (int, optional): Inflation rate in percentage. Defaults to 3.
        betrachtungszeitraum (int, optional): Consideration period in years. Defaults to 20.
        stundensatz (int, optional): Hourly rate for labor in €/h. Defaults to 45.

    Returns:
        dict: Results of the energy generation mix calculation, including heat demand, cost, emissions, and other metrics.
    """
    q, r, T = calculate_factors(kapitalzins, preissteigerungsrate, betrachtungszeitraum)
    time_steps, Last_L, VLT_L, RLT_L = initial_data

    duration = np.diff(time_steps[0:2]) / np.timedelta64(1, 'h')
    duration = duration[0]

    general_results = {
        'time_steps': time_steps,
        'Last_L': Last_L,
        'VLT_L': VLT_L,
        'RLT_L': RLT_L,
        'Jahreswärmebedarf': (np.sum(Last_L)/1000) * duration,
        'WGK_Gesamt': 0,
        'Restwärmebedarf': (np.sum(Last_L)/1000) * duration,
        'Restlast_L': Last_L.copy(),
        'Wärmeleistung_L': [],
        'colors': [],
        'Wärmemengen': [],
        'Anteile': [],
        'WGK': [],
        'Strombedarf': 0,
        'Strommenge': 0,
        'el_Leistungsbedarf_L': np.zeros_like(Last_L),
        'el_Leistung_L': np.zeros_like(Last_L),
        'el_Leistung_ges_L': np.zeros_like(Last_L),
        'specific_emissions_L': [],
        'primärenergie_L': [],
        'specific_emissions_Gesamt': 0,
        'primärenergiefaktor_Gesamt': 0,
        'techs': [],
        'tech_classes': []
    }

    for idx, tech in enumerate(tech_order.copy()):
        if len(variables) > 0:
            if tech.name.startswith("Solarthermie"):
                tech.bruttofläche_STA = variables[variables_order.index(f"bruttofläche_STA_{idx}")]
                tech.vs = variables[variables_order.index(f"vs_{idx}")]
            elif tech.name.startswith("Abwärme") or tech.name.startswith("Abwasserwärme"):
                tech.Kühlleistung_Abwärme = variables[variables_order.index(f"Kühlleistung_Abwärme_{idx}")]
            elif tech.name.startswith("Flusswasser"):
                tech.Wärmeleistung_FW_WP = variables[variables_order.index(f"Wärmeleistung_FW_WP_{idx}")]
            elif tech.name.startswith("Geothermie"):
                tech.Fläche = variables[variables_order.index(f"Fläche_{idx}")]
                tech.Bohrtiefe = variables[variables_order.index(f"Bohrtiefe_{idx}")]
            elif tech.name.startswith("BHKW") or tech.name.startswith("Holzgas-BHKW"):
                tech.th_Leistung_BHKW = variables[variables_order.index(f"th_Leistung_BHKW_{idx}")]
                if tech.speicher_aktiv:
                    tech.Speicher_Volumen_BHKW = variables[variables_order.index(f"Speicher_Volumen_BHKW_{idx}")]
            elif tech.name.startswith("Biomassekessel"):
                tech.P_BMK = variables[variables_order.index(f"P_BMK_{idx}")]

        if tech.name.startswith("Solarthermie"):
            tech_results = tech.calculate(VLT_L, RLT_L, TRY, time_steps, start, end, q, r, T, BEW, stundensatz, duration, general_results)
        elif tech.name.startswith("Abwärme") or tech.name.startswith("Abwasserwärme"):
            tech_results = tech.calculate(VLT_L, COP_data, Strompreis, q, r, T, BEW, stundensatz, duration, general_results)
        elif tech.name.startswith("Flusswasser"):
            tech_results = tech.calculate(VLT_L, COP_data, Strompreis, q, r, T, BEW, stundensatz, duration, general_results)
        elif tech.name.startswith("Geothermie"):
            tech_results = tech.calculate(VLT_L, COP_data, Strompreis, q, r, T, BEW, stundensatz, duration, general_results)
        elif tech.name.startswith("BHKW") or tech.name.startswith("Holzgas-BHKW"):
            tech_results = tech.calculate(Gaspreis, Holzpreis, Strompreis, q, r, T, BEW, stundensatz, duration, general_results)
        elif tech.name.startswith("Biomassekessel"):
            tech_results = tech.calculate(Holzpreis, q, r, T, BEW, stundensatz, duration, general_results)
        elif tech.name.startswith("Gaskessel"):
            tech_results = tech.calculate(Gaspreis, q, r, T, BEW, stundensatz, duration, Last_L, general_results)
        elif tech.name.startswith("AqvaHeat"):
            tech_results = tech.calculate(VLT_L, COP_data, duration, general_results)
        else:
            tech_order.remove(tech)
            print(f"{tech.name} ist kein gültiger Erzeugertyp und wird daher nicht betrachtet.")

        if tech_results['Wärmemenge'] > 0:
            general_results['Wärmeleistung_L'].append(tech_results['Wärmeleistung_L'])
            general_results['Wärmemengen'].append(tech_results['Wärmemenge'])
            general_results['Anteile'].append(tech_results['Wärmemenge']/general_results['Jahreswärmebedarf'])
            general_results['WGK'].append(tech_results['WGK'])
            general_results['specific_emissions_L'].append(tech_results['spec_co2_total'])
            general_results['primärenergie_L'].append(tech_results['primärenergie'])
            general_results['colors'].append(tech_results['color'])
            general_results['Restlast_L'] -= tech_results['Wärmeleistung_L']
            general_results['Restwärmebedarf'] -= tech_results['Wärmemenge']
            general_results['WGK_Gesamt'] += (tech_results['Wärmemenge']*tech_results['WGK'])/general_results['Jahreswärmebedarf']
            general_results['specific_emissions_Gesamt'] += (tech_results['Wärmemenge']*tech_results['spec_co2_total'])/general_results['Jahreswärmebedarf']
            general_results['primärenergiefaktor_Gesamt'] += tech_results['primärenergie']/general_results['Jahreswärmebedarf']

            if tech.name.startswith("BHKW") or tech.name.startswith("Holzgas-BHKW"):
                general_results['Strommenge'] += tech_results["Strommenge"]
                general_results['el_Leistung_L'] += tech_results["el_Leistung_L"]
                general_results['el_Leistung_ges_L'] += tech_results["el_Leistung_L"]

            if tech.name.startswith("Abwärme") or tech.name.startswith("Abwasserwärme") or tech.name.startswith("Flusswasser") or tech.name.startswith("Geothermie"):
                general_results['Strombedarf'] += tech_results["Strombedarf"]
                general_results['el_Leistungsbedarf_L'] += tech_results["el_Leistung_L"]
                general_results['el_Leistung_ges_L'] -= tech_results['el_Leistung_L']

            if "Wärmeleistung_Speicher_L" in tech_results.keys():
                general_results['Restlast_L'] -= tech_results['Wärmeleistung_Speicher_L']

        else:
            tech_order.remove(tech)
            print(f"{tech.name} wurde durch die Optimierung entfernt.")

    for tech in tech_order:
        general_results['techs'].append(tech.name)
        general_results['tech_classes'].append(tech)

    return general_results

def optimize_mix(tech_order, initial_data, start, end, TRY, COP_data, Gaspreis, Strompreis, Holzpreis, BEW, kapitalzins, preissteigerungsrate, betrachtungszeitraum, stundensatz, weights):
    """
    Optimize the energy generation mix for minimal cost, emissions, and primary energy use.

    Args:
        tech_order (list): List of technology objects to be considered.
        initial_data (tuple): Initial data including time steps, load profile, flow temperature, and return temperature.
        start (int): Start time step for the optimization.
        end (int): End time step for the optimization.
        TRY (object): Test Reference Year data for temperature and solar radiation.
        COP_data (object): Coefficient of Performance data for heat pumps.
        Gaspreis (float): Gas price in €/kWh.
        Strompreis (float): Electricity price in €/kWh.
        Holzpreis (float): Biomass price in €/kWh.
        BEW (float): Specific CO2 emissions for electricity in kg CO2/kWh.
        kapitalzins (float): Capital interest rate in percentage.
        preissteigerungsrate (float): Inflation rate in percentage.
        betrachtungszeitraum (int): Consideration period in years.
        stundensatz (float): Hourly rate for labor in €/h.
        weights (dict): Weights for different optimization criteria.

    Returns:
        list: Optimized list of technology objects with updated parameters.
    """
    initial_values = []
    variables_order = []
    bounds = []
    for idx, tech in enumerate(tech_order):
        if isinstance(tech, SolarThermal):
            initial_values.append(tech.bruttofläche_STA)
            variables_order.append(f"bruttofläche_STA_{idx}")
            bounds.append((tech.opt_area_min, tech.opt_area_max))

            initial_values.append(tech.vs)
            variables_order.append(f"vs_{idx}")
            bounds.append((tech.opt_volume_min, tech.opt_volume_max))

        elif isinstance(tech, CHP):
            initial_values.append(tech.th_Leistung_BHKW)
            variables_order.append(f"th_Leistung_BHKW_{idx}")
            bounds.append((tech.opt_BHKW_min, tech.opt_BHKW_max))

            if tech.speicher_aktiv == True:
                initial_values.append(tech.Speicher_Volumen_BHKW)
                variables_order.append(f"Speicher_Volumen_BHKW_{idx}")
                bounds.append((tech.opt_BHKW_Speicher_min, tech.opt_BHKW_Speicher_max))

        elif isinstance(tech, BiomassBoiler):
            initial_values.append(tech.P_BMK)
            variables_order.append(f"P_BMK_{idx}")
            bounds.append((tech.opt_BMK_min, tech.opt_BMK_max))

            if tech.speicher_aktiv == True:
                initial_values.append(tech.Speicher_Volumen)
                variables_order.append(f"Speicher_Volumen_{idx}")
                bounds.append((tech.opt_Speicher_min, tech.opt_Speicher_max))

        elif isinstance(tech, Geothermal):
            initial_values.append(tech.Fläche)
            variables_order.append(f"Fläche_{idx}")
            min_area_geothermal = 0
            max_area_geothermal = 5000
            bounds.append((min_area_geothermal, max_area_geothermal))

            initial_values.append(tech.Bohrtiefe)
            variables_order.append(f"Bohrtiefe_{idx}")
            min_area_depth = 0
            max_area_depth = 400
            bounds.append((min_area_depth, max_area_depth))

        elif isinstance(tech, WasteHeatPump):
            initial_values.append(tech.Kühlleistung_Abwärme)
            variables_order.append(f"Kühlleistung_Abwärme_{idx}")
            min_cooling = 0
            max_cooling = 500
            bounds.append((min_cooling, max_cooling))

        elif isinstance(tech, RiverHeatPump):
            initial_values.append(tech.Wärmeleistung_FW_WP)
            variables_order.append(f"Wärmeleistung_FW_WP_{idx}")
            min_power_river = 0
            max_power_river = 1000
            bounds.append((min_power_river, max_power_river))


    def objective(variables):
        general_results = Berechnung_Erzeugermix(tech_order, initial_data, start, end, TRY, COP_data, Gaspreis, Strompreis, Holzpreis, BEW, variables, variables_order, \
                                            kapitalzins=kapitalzins, preissteigerungsrate=preissteigerungsrate, betrachtungszeitraum=betrachtungszeitraum, stundensatz=stundensatz)
        
        # Skalierung der Zielgrößen basierend auf ihren erwarteten Bereichen
        wgk_scale = 1.0  # Annahme: Wärmegestehungskosten liegen im Bereich von 0 bis 300 €/MWh
        co2_scale = 1000  # Annahme: Spezifische Emissionen liegen im Bereich von 0 bis 1 tCO2/MWh
        primary_energy_scale = 100.0  # Annahme: Primärenergiefaktor liegt im Bereich von 0 bis 3

        weighted_sum = (weights['WGK_Gesamt'] * general_results['WGK_Gesamt'] * wgk_scale +
                        weights['specific_emissions_Gesamt'] * general_results['specific_emissions_Gesamt'] * co2_scale +
                        weights['primärenergiefaktor_Gesamt'] * general_results['primärenergiefaktor_Gesamt'] * primary_energy_scale)
        
        return weighted_sum
    
    # optimization
    result = minimize(objective, initial_values, method='SLSQP', bounds=bounds, options={'maxiter': 100})

    if result.success:
        optimized_values = result.x
        optimized_objective = objective(optimized_values)
        print(f"Optimierte Werte: {optimized_values}")
        print(f"Minimierte gewichtete Summe: {optimized_objective:.2f}")

        for idx, tech in enumerate(tech_order):
            if isinstance(tech, SolarThermal):
                tech.bruttofläche_STA = optimized_values[variables_order.index(f"bruttofläche_STA_{idx}")]
                tech.vs = optimized_values[variables_order.index(f"vs_{idx}")]
            elif isinstance(tech, BiomassBoiler):
                tech.P_BMK = optimized_values[variables_order.index(f"P_BMK_{idx}")]
                if tech.speicher_aktiv:
                    tech.Speicher_Volumen = optimized_values[variables_order.index(f"Speicher_Volumen_{idx}")]
            elif isinstance(tech, CHP):
                tech.th_Leistung_BHKW = optimized_values[variables_order.index(f"th_Leistung_BHKW_{idx}")]
                if tech.speicher_aktiv:
                    tech.Speicher_Volumen_BHKW = optimized_values[variables_order.index(f"Speicher_Volumen_BHKW_{idx}")]
            elif isinstance(tech, Geothermal):
                tech.Fläche = optimized_values[variables_order.index(f"Fläche_{idx}")]
                tech.Bohrtiefe = optimized_values[variables_order.index(f"Bohrtiefe_{idx}")]
            elif isinstance(tech, WasteHeatPump):
                tech.Kühlleistung_Abwärme = optimized_values[variables_order.index(f"Kühlleistung_Abwärme_{idx}")]
            elif isinstance(tech, RiverHeatPump):
                tech.Wärmeleistung_FW_WP = optimized_values[variables_order.index(f"Wärmeleistung_FW_WP_{idx}")]

        return tech_order
    else:
        print("Optimierung nicht erfolgreich")
        print(result.message)

# Diese Klasse ist noch nicht fertig implementiert und die Nutzung auch noch nicht durchdacht, Wie muss dass ganze bilanziert werden?
class Photovoltaics:
    def __init__(self, name, TRY_data, Gross_area, Longitude, STD_Longitude, Latitude, East_West_collector_azimuth_angle=0, Collector_tilt_angle=36, Albedo=0.2, Kosten_STA_spez=300):
        self.name = name
        self.TRY_data = TRY_data
        self.Gross_area = Gross_area
        self.Longitude = Longitude
        self.STD_Longitude = STD_Longitude
        self.Latitude = Latitude
        self.East_West_collector_azimuth_angle = East_West_collector_azimuth_angle
        self.Collector_tilt_angle = Collector_tilt_angle
        self.Albedo = Albedo
        self.Kosten_STA_spez = Kosten_STA_spez
        self.Nutzungsdauer = 20 # Jahre
        self.f_Inst, self.f_W_Insp, self.Bedienaufwand = 0.5, 1, 0
        self.Anteil_Förderung_BEW = 0.4
        self.Betriebskostenförderung_BEW = 10 # €/MWh 10 Jahre
        self.co2_factor_solar = 0.0 # tCO2/MWh heat is 0 ?
        self.primärenergiefaktor = 0.0

    def calc_WGK(self, q=1.05, r=1.03, T=20, BEW="Nein"):
        if self.strommenge_MWh == 0:
            return 0

        self.Kosten_STA_spez = 100 # €/m²

        self.Investitionskosten = self.Gross_area * self.Kosten_STA_spez

        self.A_N = annuität(self.Investitionskosten, self.Nutzungsdauer, self.f_Inst, self.f_W_Insp, self.Bedienaufwand, q, r, T)
        self.WGK = self.A_N / self.strommenge_MWh

        self.Eigenanteil = 1 - self.Anteil_Förderung_BEW
        self.Investitionskosten_Gesamt_BEW = self.Investitionskosten * self.Eigenanteil
        self.Annuität_BEW = annuität(self.Investitionskosten_Gesamt_BEW, self.Nutzungsdauer, self.f_Inst, self.f_W_Insp, self.Bedienaufwand, q, r, T)
        self.WGK_BEW = self.Annuität_BEW / self.strommenge_MWh

        self.WGK_BEW_BKF = self.WGK_BEW - self.Betriebskostenförderung_BEW  # €/MWh 10 Jahre

        if BEW == "Nein":
            return self.WGK
        elif BEW == "Ja":
            return self.WGK_BEW_BKF
        
    def calculate(self, q, r, T, BEW):
        # Hier fügen Sie die spezifische Logik für die PV-Berechnung ein
        self.strommenge_kWh, self.P_max, self.P_L = Calculate_PV(self.TRY_data, self.Gross_area, self.Longitude, self.STD_Longitude, self.Latitude, self.Albedo, self.East_West_collector_azimuth_angle, self.Collector_tilt_angle)
        self.strommenge_MWh = self.strommenge_kWh / 1000
        self.WGK_PV = self.calc_WGK(q, r, T, BEW)

        # Berechnung der Emissionen
        self.co2_emissions = self.strommenge_MWh * self.co2_factor_solar # tCO2
        # specific emissions heat
        self.spec_co2_total = self.co2_emissions / self.strommenge_MWh if self.strommenge_MWh > 0 else 0 # tCO2/MWh_heat

        self.primärenergie_Solarthermie = self.strommenge_MWh * self.primärenergiefaktor

        results = { 
            'Strommenge': self.strommenge_kWh,
            'el_Leistung_L': self.P_L,
            'WGK': self.WGK_PV,
            'spec_co2_total': self.spec_co2_total,
            'primärenergie': self.primärenergie_Solarthermie,
            'color': "yellow"
        }

        return results
    
# Idee Photovoltaisch-Thermische-Anlagen (PVT) mit zu simulieren
class PVT:
    def __init__(self, area):
        self.area = area

    def calculate(self):
        pass

