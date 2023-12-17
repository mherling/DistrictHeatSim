import pandapipes.plotting as pp_plot
import matplotlib.pyplot as plt
import geopandas as gpd


from net_simulation_pandapipes.net_generation_test import initialize_test_net
from net_simulation_pandapipes.net_simulation_calculation import create_network, correct_flow_directions, optimize_diameter_parameters, optimize_diameter_types
import net_simulation_pandapipes.net_simulation_calculation as nsp

def config_plot(net):
    # Plotten Sie das Netzwerk
    pp_plot.simple_plot(net, junction_size=0.01, heat_exchanger_size=0.1, pump_size=0.1, \
                        pump_color='green', pipe_color='black', heat_exchanger_color='blue', \
                        show_plot=False)  # Setzen Sie show_plot auf False, um den Plot später anzuzeigen

    # Kombinieren Sie die Ergebnisse und Namen, und zeigen Sie sie im Plot an
    for junction in net.junction.index:
        # Holen Sie sich die Koordinaten
        x, y = net.junction_geodata.loc[junction, ['x', 'y']]
        # Holen Sie sich den Namen
        name = net.junction.loc[junction, 'name']
        # Holen Sie sich die Ergebnisse
        pressure = net.res_junction.loc[junction, 'p_bar']
        temperature = net.res_junction.loc[junction, 't_k']
        # Erstellen Sie die Anzeigezeichenkette
        display_text = f"{name}\nP: {pressure:.2f} bar\nT: {temperature - 273.15:.2f} °C"
        # Zeigen Sie den Text im Plot an
        plt.text(x, y, display_text, ha='center', va='bottom', fontsize=8)

    # Massenstrom und Strömungsgeschwindigkeit an Pipes anzeigen
    for pipe in net.pipe.index:
        # Finde die Start- und End-Junction der Pipe
        from_junction = net.pipe.at[pipe, 'from_junction']
        to_junction = net.pipe.at[pipe, 'to_junction']
        
        # Finde die Koordinaten der Start- und End-Junction
        from_x, from_y = net.junction_geodata.loc[from_junction, ['x', 'y']]
        to_x, to_y = net.junction_geodata.loc[to_junction, ['x', 'y']]
        
        # Berechne den Mittelpunkt der Pipe
        mid_x = (from_x + to_x) / 2
        mid_y = (from_y + to_y) / 2
        
        # pipe type
        pipe_type = net.pipe.loc[pipe, 'std_type']

        # Länge Pipe
        pipe_length_km = net.pipe.loc[pipe, 'length_km']

        # Ergebnisse für die Pipe abrufen
        mdot = net.res_pipe.loc[pipe, 'mdot_from_kg_per_s']
        v = net.res_pipe.loc[pipe, 'v_mean_m_per_s']
        
        # Anzeigezeichenkette erstellen
        display_text = f"type: {pipe_type}\nlength: {pipe_length_km:.2f} km\nMdot: {mdot:.2f} kg/s\nV: {v:.2f} m/s"
        
        # Text im Plot anzeigen
        plt.text(mid_x, mid_y, display_text, ha='center', va='top', fontsize=8, color='red')

        # Informationen für flow_controls anzeigen

    for fc in net.flow_control.index:
        # Koordinaten des flow_controls
        x, y = net.junction_geodata.loc[net.flow_control.at[fc, 'from_junction'], ['x', 'y']]
        
        # Ergebnisse abrufen
        mdot = net.res_flow_control.loc[fc, 'mdot_from_kg_per_s']
        v = net.res_flow_control.loc[fc, 'v_mean_m_per_s']
        
        # Anzeigezeichenkette erstellen
        display_text = f"Flow Control\nMdot: {mdot:.2f} kg/s\nV: {v:.2f} m/s"
        
        # Text im Plot anzeigen
        plt.text(x, y, display_text, ha='center', va='top', fontsize=8, color='blue')

    # Informationen für heat_exchangers anzeigen
    for hx in net.heat_exchanger.index:
        # Koordinaten des heat_exchangers
        x, y = net.junction_geodata.loc[net.heat_exchanger.at[hx, 'from_junction'], ['x', 'y']]
        
        # Ergebnisse abrufen
        mdot = net.res_heat_exchanger.loc[hx, 'mdot_from_kg_per_s']
        v = net.res_heat_exchanger.loc[hx, 'v_mean_m_per_s']
        qext = net.heat_exchanger.loc[hx, 'qext_w']
        
        # Anzeigezeichenkette erstellen
        display_text = f"Heat Exchanger\nMdot: {mdot:.2f} kg/s\nV: {v:.2f} m/s\nQext: {qext:.2f} W"
        
        # Text im Plot anzeigen
        plt.text(x, y, display_text, ha='center', va='top', fontsize=8, color='green')
    
    # Zeigen Sie den Plot an
    plt.show()

def generate_net(qext_w=83000, pipe_creation_mode="type"):
    gdf_vl = gpd.read_file('net_generation_QGIS/Beispiel Zittau 2/Vorlauf.geojson')
    gdf_rl = gpd.read_file('net_generation_QGIS/Beispiel Zittau 2/Rücklauf.geojson')
    gdf_HAST = gpd.read_file('net_generation_QGIS/Beispiel Zittau 2/HAST.geojson')
    gdf_WEA = gpd.read_file('net_generation_QGIS/Beispiel Zittau 2/Erzeugeranlagen.geojson')

    net = nsp.create_network(gdf_vl, gdf_rl, gdf_HAST, gdf_WEA, qext_w, pipe_creation_mode)

    net_corrected_flow = correct_flow_directions(net)
    net_optimized_diameters = optimize_diameter_types(net_corrected_flow)
    net_optimized_diameters = optimize_diameter_parameters(net_optimized_diameters, element="heat_exchanger", v_max=2, v_min=1.8)
    net_optimized_diameters = optimize_diameter_parameters(net_optimized_diameters, element="flow_control", v_max=2, v_min=1.8)

    

    return net, net_corrected_flow, net_optimized_diameters

def generate_test_net():
    net = initialize_test_net()
    config_plot(net)

    ptimized_net = optimize_diameter_types(net)
    config_plot(optimized_net)

    optimized_net = optimize_diameter_parameters(optimized_net, element="heat_exchanger", v_max=2, v_min=1.8)
    optimized_net = optimize_diameter_parameters(optimized_net, element="flow_control", v_max=2, v_min=1.8)

    config_plot(optimized_net)

#generate_test_net()

#gis_net, gis_net_corrected_flow, gis_net_optimized_diameters = generate_net()

#config_plot(gis_net_optimized_diameters)

