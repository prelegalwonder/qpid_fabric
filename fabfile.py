from fabric.operations import *
from fabric.api import *
import socket
import sys
import string
import augeas

def cluster_conf(members,host):
    os.mkdir('/tmp/'+host+'/etc/cluster')
    file = open('/tmp/'+host+'/etc/cluster/cluster.conf','w')
    file.write('<?xml version="1.0" ?>\n')
    file.write('  <cluster config_version="1" name="test">\n')
    file.write('    <clusternodes>\n')

    loopid = 1
    for member in members.iterkeys():
        #nodeid = members.index(member)+1
	nodeid = loopid
	loopid = loopid+1
        file.write('      <clusternode name="'+member+'" nodeid="'+str(nodeid)+'" votes="1"/>\n')
	
    file.write('    </clusternodes>\n')
    file.write('\n')
    file.write('    <cman/>\n')
    file.write('    <rm log_level="7">\n')
    file.write('\n')
    file.write('      <failoverdomains>\n')

    loopid = 1
    for member in members.iterkeys():
        #nodeid = members.index(member)+1
        nodeid = loopid
	loopid = loopid +1
        file.write('        <failoverdomain name="only_broker'+str(nodeid)+'" restricted="1">\n')
        file.write('          <failoverdomainnode name="'+member+'"/>\n')
        file.write('        </failoverdomain>\n')
	file.write('\n')

    file.write('      </failoverdomains>\n')
    file.write('\n')
    file.write('      <resources>\n')
    file.write('        <script name="qpidd" file="/etc/init.d/qpidd" />\n')
    file.write('      </resources>\n')
    file.write('\n')

    loopid = 1
    for member in members.iterkeys():
        #nodeid = members.index(member)+1
        nodeid = loopid
	loopid = loopid+1
        file.write('      <service name="qpidd_broker'+str(nodeid)+'" domain="only_broker'+str(nodeid)+'">\n')
        file.write('        <script ref="qpidd" />\n')
        file.write('      </service>\n')
	file.write('\n')
	
    file.write('  </rm>\n')
    file.write('</cluster>\n')
    file.close()
    put('/tmp/'+env.host_string+'/etc/cluster/cluster.conf','/etc/cluster/cluster.conf')

def get_addr():
    run('ip addr | grep `netstat -nr | grep UG | awk \'{print $2}\' | cut -f1-3 -d.` | awk \'{print $2}\' | cut -f1 -d/')

def ptr_lookup(host):
    ipaddr = socket.gethostbyname_ex(host)[2]
    return ipaddr

def get_remote_configs():
    get('/etc/qpidd.conf','/tmp/'+env.host_string+'/etc/qpidd.conf')
    get('/etc/security/limits.conf','/tmp/'+env.host_string+'/etc/security/limits.conf')
    get('/etc/hosts','/tmp/'+env.host_string+'/etc/hosts')
    get('/etc/corosync/corosync.conf.example','/tmp/'+env.host_string+'/etc/corosync/corosync.conf')

def qpidd_cluster_config():
    addr = members.itervalues().next().split('.')
    bindaddr = addr[0]+'.'+addr[1]+'.'+addr[2]+'.0'
    aug = augeas.Augeas(root='/tmp/'+env.host_string)
    aug.clear_transforms()
    aug.add_transform('@Qpid','/etc/qpidd.conf')
    aug.add_transform('@Corosync','/etc/corosync/corosync.conf')
    aug.load()
    aug.set("/files/etc/qpidd.conf/auth","no")
    aug.set("/files/etc/qpidd.conf/cluster-cman","yes")
    aug.set("/files/etc/qpidd.conf/cluster-name",cluster)
    aug.set("/files/etc/qpidd.conf/log-enable","debug")
    aug.set("/files/etc/qpidd.conf/log-to-file","/tmp/qpidd.log")
    aug.set("/files/etc/corosync/corosync.conf/totem/interface/bindnetaddr",bindaddr)
    try:
        aug.save()
    except:
        error = str(aug.match("/augeas//error")[0])
        print "Error Path: "+error
        print aug.get(error+'/message')
    put('/tmp/'+env.host_string+'/etc/qpidd.conf','/etc/qpidd.conf')
    put('/tmp/'+env.host_string+'/etc/corosync/corosync.conf','/etc/corosync/corosync.conf')
    put('/home/areplogle/scripts/etc/init.d/qpidd','/etc/init.d/qpidd')
    run('chown -R root:root /var/lib/qpidd')
    run('chown -R root:root /var/run/qpidd')

def mod_hosts():
    aug = augeas.Augeas(root='/tmp/'+env.host_string)
    for member in members.iterkeys():
	node = 00+int(members[member].split('.')[3])
        aug.set("/files/etc/hosts/"+str(node)+"/ipaddr",members[member])
        aug.set("/files/etc/hosts/"+str(node)+"/canonical",member)
        try:
            aug.save()
        except:
            error = str(aug.match("/augeas//error")[0])
            print "Error Path: "+error
            print aug.get(error+'/message')
	    break
    put('/tmp/'+env.host_string+'/etc/hosts','/etc/hosts')


def install_single():
    req = prereq_check()
    if (req[0] == 1 and req[1] == 1):
	run('yum -y groupinstall "MRG Messaging"')
	run('yum -y install qpid-tools')
    else:
	print env.host_string+" does not meet the prerequisites."
	print 'Please add the following RHN Channels -' 
	print '    '+req[3]
	print '    '+req[4]+'\n\n'
	sys.exit()

	
def prereq_check():
    platform = str(run('uname -p'))
    major_ver = str(run("cat /etc/redhat-release | awk '{print $7}' | cut -f1 -d."))
    mrg_chn = "rhel-"+platform+"-server-"+major_ver+"-mrg-messaging-2"
    mrg_req = 0
    ha_chn = "rhel-"+platform+"-server-ha-"+major_ver
    ha_req = 0
    opt_chn = "rhel-"+platform+"-server-optional-"+major_ver
    opt_req = 0
    channels = []
    foo = str(run('rhn-channel --list')).split('\n')
    for channel in foo:
       channels.append(channel.split('\r')[0])
    if channels.count(mrg_chn) > 0:
        mrg_req = 1
    if channels.count(opt_chn) > 0:
	opt_req = 1
    if channels.count(ha_chn) > 0:
	ha_req = 1
    return mrg_req, opt_req, ha_req, mrg_chn, opt_chn, ha_chn

def install_cluster():
    req = prereq_check()
    if (req[0] == 1 and req[1] == 1 and req[2] == 1):
        run('yum -y groupinstall "High Availability"')
	run('yum -y groupinstall "MRG Messaging"')
	run('yum -y install qpid-tools')
	run('yum -y install qpid-cpp-server-cluster')
    else:
	print env.host_string+" does not meet the prerequisites."
	print 'Please add the following RHN Channels -' 
	print '    '+req[3]
	print '    '+req[4]
	print '    '+req[5]+'\n\n'
	sys.exit()
    cluster_setup()

def cluster_setup():
    run('service corosync stop')
    run('chkconfig corosync off')
    run('service iptables stop')
    run('chkconfig iptables off')
    #run('service NetworkManager stop')
    #run('chkconfig NetworkManager off')
    get_remote_configs()
    qpidd_cluster_config()
    cluster_conf(members,env.host_string)
    mod_hosts()
    run('service cman start')
    run('chkconfig cman on')
    run('service rgmanager start')
    run('chkconfig rgmanager on')
    run('setenforce permissive')

if sys.argv[-1] == 'install_cluster':
    cluster = raw_input('Cluster Name: ')
    membercnt = int(raw_input('Number of cluster members: '))
    loopcount = 1 
    members = {}

    while membercnt > 0:
	#members.append(raw_input('Host number '+str(loopcount)+': ') )
	member = raw_input('Host number '+str(loopcount)+': ')
	ipaddy = ptr_lookup(member)[0]
	members[member] = ipaddy
	membercnt = membercnt - 1
	loopcount = loopcount + 1
        
