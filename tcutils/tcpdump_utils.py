# utils to start and stop tcpdump on VM
from common import log_orig as contrail_logging

from util import retry
from tcutils.commands import ssh, execute_cmd, execute_cmd_out
from tcutils.util import get_random_name

def start_tcpdump_for_intf(ip, username, password, interface, filters='-v', logger=None):
    if not logger:
        logger = contrail_logging.getLogger(__name__)
    session = ssh(ip, username, password)
    pcap = '/tmp/%s_%s.pcap' % (interface, get_random_name())
    cmd = 'tcpdump -ni %s -U %s -w %s' % (interface, filters, pcap)
    execute_cmd(session, cmd, logger)
    return (session, pcap)

def stop_tcpdump_for_intf(session, pcap, logger=None):
    if not logger:
        logger = contrail_logging.getLogger(__name__)
    cmd = 'kill $(ps -ef|grep tcpdump | grep pcap| awk \'{print $2}\')'
    execute_cmd(session, cmd, logger)
    return True

def start_tcpdump_for_vm_intf(obj, vm_fix, vn_fq_name, filters='-v', pcap_on_vm=False, vm_intf='eth0'):
    if not pcap_on_vm:
        compute_ip = vm_fix.vm_node_ip
        compute_user = obj.inputs.host_data[compute_ip]['username']
        compute_password = obj.inputs.host_data[compute_ip]['password']
        vm_tapintf = obj.orch.get_vm_tap_interface(vm_fix.tap_intf[vn_fq_name])
        return start_tcpdump_for_intf(compute_ip, compute_user,
            compute_password, vm_tapintf, filters, logger=obj.logger)
    else:
        pcap = '/tmp/%s.pcap' % (get_random_name())
        cmd_to_tcpdump = [ 'tcpdump -ni %s %s -w %s 1>/dev/null 2>/dev/null' % (vm_intf, filters, pcap) ]
        pidfile = pcap + '.pid'
        vm_fix_pcap_pid_files =[]
        for vm_fixture in vm_fix:
            vm_fixture.run_cmd_on_vm(cmds=cmd_to_tcpdump, as_daemon=True, pidfile=pidfile, as_sudo=True)
            vm_fix_pcap_pid_files.append((vm_fixture, pcap, pidfile))
        return vm_fix_pcap_pid_files
# end start_tcpdump_for_vm_intf

def stop_tcpdump_for_vm_intf(obj, session, pcap, vm_fix_pcap_pid_files=[], filters=''):
    if not vm_fix_pcap_pid_files:
        return stop_tcpdump_for_intf(session, pcap, logger=obj.logger)
    else:
        output = []
        pkt_count = []
        for vm_fix, pcap, pidfile in vm_fix_pcap_pid_files:
            cmd_to_output  = 'tcpdump -nr %s %s' % (pcap, filters)
            cmd_to_kill = 'cat %s | xargs kill ' % (pidfile)
            count = cmd_to_output + '| wc -l'
            vm_fix.run_cmd_on_vm(cmds=[cmd_to_kill], as_sudo=True)
            vm_fix.run_cmd_on_vm(cmds=[cmd_to_output], as_sudo=True)
            output.append(vm_fix.return_output_cmd_dict[cmd_to_output])
            vm_fix.run_cmd_on_vm(cmds=[count], as_sudo=True)
            pkt_count.append(vm_fix.return_output_cmd_dict[count].split('\n')[2])
            return output, pkt_count
# end stop_tcpdump_for_vm_intf

def read_tcpdump(obj, session, pcap):
    cmd = 'tcpdump -n -r %s' % pcap
    out, err = execute_cmd_out(session, cmd, obj.logger)
    return out

@retry(delay=2, tries=6)
def verify_tcpdump_count(obj, session, pcap, exp_count=None, exact_match=True, mac=None):

    if mac:
        cmd = 'tcpdump -r %s | grep %s | wc -l' % (pcap,mac)
    else:
        cmd = 'tcpdump -r %s | wc -l' % pcap
    out, err = execute_cmd_out(session, cmd, obj.logger)
    count = int(out.strip('\n'))
    result = True
    if exp_count is not None:
        if count != exp_count and exact_match:
            obj.logger.warn("%s packets are found in tcpdump output file %s but \
                                        expected %s" % (count, pcap, exp_count))
            result = False
        elif count > exp_count and not exact_match:
            obj.logger.debug("%s packets are found in tcpdump output file %s but \
                             expected %s, which is fine" % (count, pcap, exp_count))
        elif count < exp_count and not exact_match:
            obj.logger.warn("%s packets are found in tcpdump output file %s but \
                             expected atleast %s" % (count, pcap, exp_count))
            result = False
    else:
        if count == 0:
            obj.logger.warn("No packets are found in tcpdump output file %s but \
                                        expected some packets" % (pcap))
            result = False

    if result:
        obj.logger.info(
            "%s packets are found in tcpdump output as expected",
            count)
        stop_tcpdump_for_vm_intf(obj, session, pcap)
    return result

def search_in_pcap(session, pcap, search_string):
    cmd = 'tcpdump -v -r %s | grep "%s"' % (pcap, search_string)
    out, err = execute_cmd_out(session, cmd)
    if search_string in out:
        return True
    else:
        return False
# end search_in_pcap

def delete_pcap(session, pcap):
    execute_cmd_out(session, 'rm -f %s' % (pcap))

