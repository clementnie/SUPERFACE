package require ::quartus::sta

project_open LAB8
create_timing_netlist -model slow
read_sdc
update_timing_netlist
report_clocks -file phase5_clocks.rpt
report_net_delay -nworst 12 -file phase5_gray_net_delays.rpt
report_ucp -file phase5_unconstrained.rpt
delete_timing_netlist
project_close
