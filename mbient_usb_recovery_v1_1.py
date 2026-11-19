#!/usr/bin/env python3
"""Experimental local MMS USB recovery. Fresh uninterrupted downloads only.
No BLE, network, reset, clear-all, teardown, or automatic crash resume.
Requires Python 3.10+ and pyserial. Run --help.
"""
import argparse, csv, hashlib, json, os, re, struct, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
try:
    import fcntl
except ImportError:
    fcntl=None
import serial
from serial.tools import list_ports

VERSION='1.1.0-experimental'
K=48/32768
DEFAULT=Path.home()/'Desktop'/'Mbient_USB_recovery'

def durable(f):
    f.flush();os.fsync(f.fileno())
    if fcntl and hasattr(fcntl,'F_FULLFSYNC'):
        fcntl.fcntl(f.fileno(),fcntl.F_FULLFSYNC)

def syncdir(p):
    if os.name=='posix':
        fd=os.open(str(p),os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)

def jwrite(p,obj):
    with p.open('x') as f: json.dump(obj,f,indent=2);durable(f)
    syncdir(p.parent)

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''): h.update(chunk)
    return h.hexdigest()

def candidates():
    return sorted([p for p in list_ports.comports() if p.vid==0x1915 and p.pid==0xd978],key=lambda p:p.device)

def select_port(arg):
    if arg: return arg
    ports=candidates()
    if not ports: raise RuntimeError('No MMS VID:PID 1915:D978 found. Use scan --all to inspect ports; do not guess a non-MMS port.')
    for i,p in enumerate(ports,1): print(f'{i}: {p.device} USB serial={p.serial_number} {p.description}')
    if len(ports)==1: return ports[0].device
    n=int(input('Select device number: '))
    if not 1<=n<=len(ports): raise RuntimeError('Invalid selection')
    return ports[n-1].device

class Link:
    def __init__(self,port,folder):
        self.folder=folder;self.buf=bytearray();self.ser=None
        self.raw=(folder/'received.bin').open('xb');self.log=(folder/'journal.jsonl').open('x')
        self.page_ready=False
        try:
            kwargs={'port':port,'baudrate':1000000,'timeout':.1,'write_timeout':3}
            if os.name=='posix': kwargs['exclusive']=True
            self.ser=serial.Serial(**kwargs)
            time.sleep(.1);self.ser.reset_input_buffer();self.ser.reset_output_buffer()
            if self.ser.write(b'?\n')!=2: raise RuntimeError('Short identity write')
            self.ser.flush()
            line=self.ser.read_until(b'\n',256)
            (folder/'identity_received.bin').write_bytes(line)
            self.identity=line.decode('ascii',errors='replace').strip()
            parts=self.identity.split()
            if len(parts)!=6 or parts[0]!='MbientLab' or parts[1]!='MetaMotionS' or parts[2]!='8':
                raise RuntimeError('Unsupported identity: '+self.identity)
            if not re.fullmatch('[A-Za-z0-9._-]+',parts[5]): raise RuntimeError('Invalid serial')
            self.device_id=parts[5];self.firmware=parts[4]
            info=next((p for p in list_ports.comports() if p.device==port),None)
            self.usb_serial=info.serial_number if info else None
            self.event('identity',identity=self.identity,port=port,usb_serial=self.usb_serial);self.sync()
        except BaseException:
            self.close();raise
    def event(self,kind,**kw):
        self.log.write(json.dumps({'epoch_s':time.time(),'event':kind,**kw})+chr(10))
    def sync(self):
        durable(self.raw);durable(self.log);syncdir(self.folder)
    def send(self,payload):
        readonly=len(payload)>=2 and bool(payload[1]&0x80)
        fixed={bytes.fromhex(h) for h in ('0b 01 00','03 01 00','13 01 00','0b 10 01','0b 07 01','0b 0d 01','0b 08 01')}
        if payload==bytes.fromhex('0b 0e'):
            if not self.page_ready: raise RuntimeError('Page confirmation blocked: no durably saved page')
            self.page_ready=False
        elif not readonly and payload not in fixed and not (len(payload)==10 and payload[:2]==bytes.fromhex('0b 06')):
            raise RuntimeError('Command not allowed: '+payload.hex())
        self.event('send_intent',hex=payload.hex());self.sync()
        wire=bytes([31,len(payload)])+payload+b'\n'
        if self.ser.write(wire)!=len(wire): raise RuntimeError('Short write; device outcome uncertain')
        self.ser.flush();self.event('write_returned',hex=payload.hex());self.sync()
    def frame(self,timeout):
        deadline=time.monotonic()+timeout
        while True:
            if self.buf:
                if self.buf[0]!=31: raise RuntimeError('Invalid prefix; raw retained, no resynchronisation guessed')
                if len(self.buf)>=2:
                    n=self.buf[1]
                    if n<2: raise RuntimeError('Invalid frame length')
                    if len(self.buf)>=n+3:
                        if self.buf[n+2]!=10: raise RuntimeError('Invalid terminator')
                        data=bytes(self.buf[2:n+2]);del self.buf[:n+3];return data
            if time.monotonic()>=deadline:
                if self.buf: raise RuntimeError('Timeout with incomplete frame')
                return None
            b=self.ser.read(max(1,min(1024,self.ser.in_waiting)))
            if b: self.raw.write(b);self.buf.extend(b)
    def query(self,h):
        cmd=bytes.fromhex(h);before=time.time();self.send(cmd);response=self.frame(6);after=time.time()
        if response is None or response[:2]!=cmd[:2]:
            raise RuntimeError('Missing/unexpected query reply for '+h+'; existing notifications may need review')
        self.event('query_reply',command=h,hex=response.hex())
        return {'command_hex':h,'response_hex':response.hex(' '),'host_before_epoch_s':before,'host_after_epoch_s':after,
                'host_midpoint_epoch_s':(before+after)/2}
    def close(self):
        try: self.sync()
        finally:
            if self.ser: self.ser.close()
            self.raw.close();self.log.close()

def metadata(link):
    m={'tool_version':VERSION,'identity':link.identity,'device_id':link.device_id,'usb_serial':link.usb_serial,
       'firmware':link.firmware,'queries':{},'logger_definitions':{}}
    try:
        for name,h in [('acc_module','03 80'),('acc_config','03 83'),('logging_module','0b 80'),('anchor','0b 84'),('length','0b 85')]:
            m['queries'][name]=link.query(h)
        # Discover only the logger slots supported by the recognized module.
        info = bytes.fromhex(
            m['queries']['logging_module']['response_hex']
        )
        expected_info = bytes.fromhex(
            '0b 80 00 03 08 00 00 00 04 00 02'
        )
        if info != expected_info:
            raise RuntimeError(
                'Unrecognized logging module layout; '
                'metadata retained, no logger scan or readout started'
            )
        slot_count = info[4]
        m['logger_slot_count'] = slot_count
        for lid in range(slot_count):
            response=link.query(f'0b 82 {lid:02x}')
            m['logger_definitions'][str(lid)]=response
    finally:
        jwrite(link.folder/'metadata.json',m)
    return m

def profile(m):
    if m['firmware'] != '1.7.2':
        raise RuntimeError('Supported firmware: 1.7.2 only')
    acc = bytes.fromhex(m['queries']['acc_module']['response_hex'])
    if acc != bytes.fromhex('03 80 04 00'):
        raise RuntimeError('Supported ACC: BMI270 implementation4 revision0 only')
    active = {}
    for lid, row in m['logger_definitions'].items():
        b = bytes.fromhex(row['response_hex'])
        if b == bytes.fromhex('0b 82'):
            continue
        if len(b) != 6:
            raise RuntimeError('Unexpected logger definition length')
        active[int(lid)] = b[2:]
    xy = sorted(lid for lid, b in active.items() if b == bytes.fromhex('03 04 ff 60'))
    z = sorted(lid for lid, b in active.items() if b == bytes.fromhex('03 04 ff 24'))
    if not active:
        raise RuntimeError('No configured loggers. No readout started; zero-length check is pre-flush only.')
    if len(active) != len(xy) + len(z):
        raise RuntimeError('Other signal definitions present. This version only handles direct ACC 4+2-byte loggers.')
    if not xy or len(xy) != len(z) or {a + 1 for a in xy} != set(z):
        raise RuntimeError('Ambiguous ACC logger allocation: adjacent XY/Z slots required; no nearest-tick guessing')
    groups = [{'xy_logger':a, 'z_logger':a+1, 'name':f'acc_ids_{a}_{a+1}'} for a in xy]
    cfg = bytes.fromhex(m['queries']['acc_config']['response_hex'])
    if len(cfg) != 4 or cfg[3] & 0xfc:
        raise RuntimeError('Unexpected current BMI270 range config')
    return {'groups':groups, 'current_range_g':[2,4,8,16][cfg[3]&3],
            'group_assignment':'candidate adjacent-ID allocation, checked against actual per-group entry order and ticks',
            'duplicate_status':'unknown until actual raw decoded; never automatically merged or deduplicated'}


def folder_new(root,kind):
    root.mkdir(parents=True,exist_ok=True)
    p=root/(kind+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));p.mkdir(exist_ok=False);return p

def decode(folder, range_g):
    from contextlib import ExitStack
    from collections import Counter
    manifest = json.loads((folder/'raw_manifest.json').read_text())
    if not manifest.get('readout_finished'):
        raise RuntimeError('Readout unfinished; raw tail must be reviewed before automated decode')
    m = json.loads((folder/'metadata.json').read_text())
    prof = profile(m)
    out = folder_new(folder, 'decoded_v1_1')
    anchor = bytes.fromhex(m['queries']['anchor']['response_hex'])
    if len(anchor) != 7:
        raise RuntimeError('Unexpected anchor response')
    atick = struct.unpack('<I', anchor[2:6])[0]
    auid = anchor[6]&7
    host = m['queries']['anchor']['host_midpoint_epoch_s']
    scale = 32768/range_g
    states = []
    by_logger = {}
    report = {'tool_version':VERSION, 'csv_complete':False,
              'historical_completeness_verified':False,
              'range_g_used':range_g, 'range_status':'current or operator-selected range; historical constancy not proven',
              'utc_status':'conditional estimate from saved anchor; UID match alone does not prove same boot',
              'tick_seconds':K, 'sample_time':'XY logger tick; Z tick retained',
              'elapsed_zero':'first successfully paired sample encountered globally; shared across groups, not LSL/experiment zero',
              'drift_correction_applied':False, 'group_assignment':prof['group_assignment'],
              'deduplication_applied':False, 'streams_merged':False, 'groups':[], 'output':str(out)}
    global_first = None
    raw_counts = Counter()
    entry_count = 0
    try:
        with ExitStack() as stack:
            files = []
            rawf = stack.enter_context((out/'all_entries_index.csv').open('x', newline=''))
            files.append(rawf)
            rawwriter = csv.writer(rawf)
            rawwriter.writerow(['entry_index','source_page','logger_id','reset_uid','tick','payload_hex','entry_hex'])
            for group in prof['groups']:
                sf = stack.enter_context((out/(group['name']+'_CANDIDATE_ESTIMATED.csv')).open('x', newline=''))
                af = stack.enter_context((out/(group['name']+'_audit.csv')).open('x', newline=''))
                files.extend([sf, af])
                w, v = csv.writer(sf), csv.writer(af)
                w.writerow(['epoch (ms)','timestamp (+0000)','elapsed (s)','x-axis (g)','y-axis (g)','z-axis (g)'])
                v.writerow(['sample_index','reset_uid','xy_tick','z_tick','pair_delta_tick','elapsed_shared_s','elapsed_from_this_group_start_s','conditional_epoch_s','x_raw','y_raw','z_raw','x_g','y_g','z_g','xy_entry_index','z_entry_index','xy_entry_hex','z_entry_hex'])
                state = dict(group, pending=None, samples=0, error=None, uid=None, first_tick=None,
                             last_tick=None, pair_deltas=Counter(), tick_steps=Counter(),
                             raw_xy=0, raw_z=0, blank_utc=0, w=w, v=v, sequence_hash=hashlib.sha256())
                states.append(state)
                by_logger[group['xy_logger']] = state
                by_logger[group['z_logger']] = state
            try:
                for item in manifest['ordered_files']:
                    path = folder/item['file']
                    if not sha_check(path, item):
                        raise RuntimeError('Raw page hash/count mismatch: '+str(path))
                    with path.open('rb') as src:
                        while True:
                            b = src.read(9)
                            if not b:
                                break
                            if len(b) != 9:
                                raise RuntimeError('Incomplete raw entry')
                            index = entry_count
                            entry_count += 1
                            lid, uid = b[0]&31, b[0]>>5
                            tick = struct.unpack('<I', b[1:5])[0]
                            raw_counts[lid] += 1
                            rawwriter.writerow([index,item['file'],lid,uid,tick,b[5:9].hex(),b.hex()])
                            state = by_logger.get(lid)
                            if state is None:
                                continue
                            if lid == state['xy_logger']:
                                state['raw_xy'] += 1
                            else:
                                state['raw_z'] += 1
                            if state['error']:
                                continue
                            try:
                                if state['uid'] is None:
                                    state['uid'] = uid
                                if state['uid'] != uid:
                                    raise RuntimeError('Reset UID changed; segment-specific reconstruction required')
                                if lid == state['xy_logger']:
                                    if state['pending'] is not None:
                                        raise RuntimeError('Second XY before Z; candidate group rejected from here')
                                    state['pending'] = (b,tick,index)
                                    continue
                                if state['pending'] is None:
                                    raise RuntimeError('Z before XY; no fabricated missing half')
                                b0,t0,i0 = state['pending']
                                delta = tick-t0
                                if delta not in (0,1):
                                    raise RuntimeError('Unexpected pair tick difference')
                                if state['last_tick'] is not None:
                                    step = t0-state['last_tick']
                                    if step <= 0:
                                        raise RuntimeError('Non-increasing tick/reset/wrap; no automatic time repair')
                                    state['tick_steps'][step] += 1
                                if state['first_tick'] is None:
                                    state['first_tick'] = t0
                                if global_first is None:
                                    global_first = t0
                                x,y,z = struct.unpack('<hhh', b0[5:9]+b[5:7])
                                g = [x/scale,y/scale,z/scale]
                                elapsed = (t0-global_first)*K
                                own_elapsed = (t0-state['first_tick'])*K
                                epoch = ms = stamp = ''
                                if uid == auid and t0 <= atick:
                                    epoch = host-(atick-t0)*K
                                    ms = round(epoch*1000)
                                    stamp = datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%Y-%m-%dT%H.%M.%S.')+f'{ms%1000:03d}'
                                else:
                                    state['blank_utc'] += 1
                                state['w'].writerow([ms,stamp,f'{elapsed:.3f}',*[f'{v:.3f}' for v in g]])
                                state['v'].writerow([state['samples'],uid,t0,tick,delta,elapsed,own_elapsed,epoch,x,y,z,*g,i0,index,b0.hex(),b.hex()])
                                # Independent of logger IDs and padding, but includes both sample ticks.
                                state['sequence_hash'].update(bytes([uid])+struct.pack('<IIhhh',t0,tick,x,y,z))
                                state['samples'] += 1
                                state['pair_deltas'][delta] += 1
                                state['last_tick'] = t0
                                state['pending'] = None
                            except Exception as exc:
                                state['error'] = str(exc)
                for state in states:
                    if state['pending'] is not None and not state['error']:
                        state['error'] = 'Final unpaired XY retained in raw; no zero filling'
            finally:
                for f in files:
                    durable(f)
    except Exception as exc:
        report['error'] = type(exc).__name__+': '+str(exc)
    for state in states:
        complete = not state['error'] and state['pending'] is None and state['samples'] > 0 and 'error' not in report
        report['groups'].append({
            'name':state['name'],'xy_logger':state['xy_logger'],'z_logger':state['z_logger'],
            'csv_complete':complete,'samples_written':state['samples'],
            'raw_xy_entries':state['raw_xy'],'raw_z_entries':state['raw_z'],
            'reset_uid':state['uid'],'first_tick':state['first_tick'],'last_tick':state['last_tick'],
            'blank_utc_rows':state['blank_utc'],'pair_delta_tick_counts':dict(state['pair_deltas']),
            'sample_tick_step_counts':dict(state['tick_steps']), 'error':state['error'],
            'pending_entry_hex':state['pending'][0].hex() if state['pending'] else None,
            'sample_sequence_sha256':state['sequence_hash'].hexdigest(),
            'interpretation':'candidate group; structural validation is not proof of logger creation history'})
    comparisons = []
    groups = report['groups']
    for i,a in enumerate(groups):
        for b in groups[i+1:]:
            comparable = a['csv_complete'] and b['csv_complete']
            exact = bool(comparable and a['samples_written'] == b['samples_written'] and
                         a['sample_sequence_sha256'] == b['sample_sequence_sha256'])
            comparisons.append({'group_a':a['name'],'group_b':b['name'],
                                'both_complete':comparable,'identical_entire_decoded_sequence':exact,
                                'interpretation':'identical decoded sequence under stated grouping' if exact else
                                'not established identical; no deduplication or merging performed'})
    report.update(raw_entries_indexed=entry_count, raw_counts_by_logger=dict(raw_counts),
                  groups_comparison=comparisons, shared_elapsed_origin_tick=global_first,
                  unassigned_logger_ids=sorted(set(raw_counts)-set(by_logger)),
                  samples_written=sum(s['samples'] for s in states),
                  samples_count_note='sum across groups, NOT unique physical samples')
    report['csv_complete'] = bool(groups) and 'error' not in report and all(g['csv_complete'] for g in groups) and not report['unassigned_logger_ids']
    jwrite(out/'decode_report.json',report)
    print(json.dumps(report,indent=2))
    return report


def sha_check(path,item):
    return digest(path)==item['sha256'] and path.stat().st_size==item['entries']*9

def retrieve(link,m,root,selected_range):
    prof=profile(m)
    identity_key=re.sub('[^A-Za-z0-9._-]','_',m['usb_serial'] or m['device_id'])
    registry=root/'device_locks';registry.mkdir(exist_ok=True)
    marker=registry/(identity_key+'.json')
    if marker.exists(): raise RuntimeError('A previous retrieval is registered for this device. No blind retry. Review marker: '+str(marker))
    print(json.dumps({'identity':m['identity'],'usb_serial':m['usb_serial'],'profile':prof,'folder':str(link.folder)},indent=2))
    print('FRESH UNINTERRUPTED RECOVERY ONLY. Previously downloaded/confirmed pages are not reconstructed automatically.')
    print('Will stop logging and ACC/gyro, flush pending NAND writes, then permanently confirm saved pages.')
    print('Do not proceed if any other recovery session already confirmed pages on this recording.')
    if input('Type FRESH '+m['device_id']+' to consent: ').strip()!='FRESH '+m['device_id']:
        raise RuntimeError('Cancelled; no stop/flush/readout/page-confirm commands sent')
    jwrite(marker,{'device':m['identity'],'usb_serial':m['usb_serial'],'folder':str(link.folder),
                   'reason':'attempt marker; retain on completion or failure; do not delete to bypass retry protection'})
    state={'readout_finished':False,'historical_completeness_verified':False,'csv_complete':False,
           'entries_received':0,'pages_saved':0,'page_confirm_writes_returned':0,'initial_length_query':m['queries']['length']}
    paths=[];page=bytearray();number=1
    def save_page(reason):
        nonlocal page,number
        path=link.folder/f'page_{number:06d}.bin';data=bytes(page)
        if not data: raise RuntimeError('Empty page')
        with path.open('xb') as f: f.write(data);durable(f)
        syncdir(link.folder)
        if path.read_bytes()!=data: raise RuntimeError('Page readback mismatch')
        item={'file':path.name,'entries':len(data)//9,'sha256':digest(path),'reason':reason}
        paths.append(item);state['pages_saved']+=1
        link.event('page_saved',page=number,**item);link.sync()
        page.clear();number+=1
    try:
        for h in ('0b 01 00','03 01 00','13 01 00','0b 10 01'):
            link.send(bytes.fromhex(h));time.sleep(.15)
        time.sleep(2)
        length=link.query('0b 85');jwrite(link.folder/'post_flush_length.json',length)
        b=bytes.fromhex(length['response_hex'])
        if len(b)!=6: raise RuntimeError('Unexpected pending length response')
        count=struct.unpack('<I',b[2:])[0];state['post_flush_reported_entries']=count
        if count==0:
            state['no_pending_entries']=True
            raise RuntimeError('Zero pending entries; no readout or confirmations sent')
        # No probe/reconnect stage: download in one uninterrupted session.
        for h in ('0b 07 01','0b 0d 01','0b 08 01'): link.send(bytes.fromhex(h))
        link.send(bytes.fromhex('0b 06')+struct.pack('<II',count,max(1,count//100)))
        zero=False;last=count;deadline=time.monotonic()+14400
        while time.monotonic()<deadline:
            packet=link.frame(3 if zero else 45)
            if packet is None:
                if not zero: raise TimeoutError('No frame before progress zero; do not retry automatically')
                if page: save_page('final_tail_unconfirmed')
                state['readout_finished']=True;state['progress_zero']=True
                state['completion_policy']='progress zero plus three-second quiet drain; not proof of historical completeness'
                link.sync();break
            if packet[:2]==bytes.fromhex('0b 07'):
                if len(packet) not in (11,20): raise RuntimeError('Unexpected raw packet length')
                page.extend(packet[2:]);state['entries_received']+=(len(packet)-2)//9
                if len(page)>4096*9: raise RuntimeError('Page safety limit reached')
            elif packet[:2]==bytes.fromhex('0b 0d'):
                if len(packet)!=2: raise RuntimeError('Invalid page-complete packet')
                save_page('page_complete')
                if not zero:
                    link.page_ready=True;link.send(bytes.fromhex('0b 0e'));state['page_confirm_writes_returned']+=1
                else: state['last_page_confirmation_withheld']=True
                if state['pages_saved']%100==0 or state['pages_saved']==1:
                    print('Saved pages:',state['pages_saved'],'received entries:',state['entries_received'],flush=True)
            elif packet[:2]==bytes.fromhex('0b 08'):
                if len(packet)!=6: raise RuntimeError('Invalid progress packet')
                remaining=struct.unpack('<I',packet[2:])[0]
                if remaining>last: raise RuntimeError('Progress increased unexpectedly')
                last=remaining;link.event('progress',remaining=remaining,received=state['entries_received'])
                if remaining==0: zero=True;link.sync()
            else: raise RuntimeError('Unexpected packet: '+packet.hex())
        else: raise TimeoutError('Four-hour runtime limit')
    except BaseException as exc:
        state['error']=type(exc).__name__+': '+str(exc)
    finally:
        try: link.sync()
        except Exception as exc: state['sync_error']=str(exc)
        state['entries_in_durable_page_files']=sum(x['entries'] for x in paths)
        state['uncommitted_page_entries_in_raw_stream']=len(page)//9
        state['difference_from_post_flush_reported_count']=state['entries_received']-state.get('post_flush_reported_entries',0)
        state['received_sha256']=digest(link.folder/'received.bin')
        jwrite(link.folder/'raw_manifest.json',{'ordered_files':paths,'readout_finished':state['readout_finished'],
               'historical_completeness_verified':False,'note':'On failure, received.bin may contain additional tail entries not in listed pages.'})
        jwrite(link.folder/'download_report.json',state)
    if state['readout_finished']:
        report=decode(link.folder,selected_range or prof['current_range_g'])
        state['csv_complete']=report['csv_complete'];state['samples_written']=report['samples_written']
        state['csv_output']=report['output']
    jwrite(link.folder/'summary.json',state);print(json.dumps(state,indent=2))
    print('OUTPUT:',link.folder)
    print('Keep all files and device lock. Never blindly retry a failed retrieval.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',action='version',version=VERSION)
    sub=parser.add_subparsers(dest='command',required=True)
    scan=sub.add_parser('scan',help='List USB descriptors only; no port opened');scan.add_argument('--all',action='store_true')
    for name in ('inspect','retrieve'):
        s=sub.add_parser(name);s.add_argument('--port');s.add_argument('--root',type=Path,default=DEFAULT)
        if name=='retrieve': s.add_argument('--range-g',type=int,choices=[2,4,8,16],help='Historical range assumption; default current BMI270 range')
    d=sub.add_parser('decode',help='Offline decode/redecode a completed folder');d.add_argument('folder',type=Path);d.add_argument('--range-g',type=int,choices=[2,4,8,16],required=True)
    args=parser.parse_args()
    if args.command=='scan':
        ports=list_ports.comports() if args.all else candidates()
        for p in ports:
            print(json.dumps({'port':p.device,'vid':f'{p.vid:04x}' if p.vid is not None else None,
                'pid':f'{p.pid:04x}' if p.pid is not None else None,'usb_serial':p.serial_number,'description':p.description}))
        print('Matching/listed ports:',len(ports));return
    if args.command=='decode':
        manifest=json.loads((args.folder/'raw_manifest.json').read_text())
        if not manifest.get('readout_finished'): raise RuntimeError('Readout did not finish; review raw tail before automated decode')
        decode(args.folder,args.range_g);return
    port=select_port(args.port);folder=folder_new(args.root,args.command);print('OUTPUT:',folder,flush=True)
    link=None
    try:
        link=Link(port,folder);m=metadata(link)
        print('Identity:',m['identity'],'USB serial:',m['usb_serial'])
        if args.command=='inspect':
            try: print('Supported profile:',profile(m))
            except Exception as exc: print('Not automatically supported:',exc)
            print('Metadata saved. No stop, NAND flush, readout or page confirm sent.')
        else: retrieve(link,m,args.root,args.range_g)
    except BaseException as exc:
        jwrite(folder/'ERROR.json',{'error':type(exc).__name__+': '+str(exc),'automatic_retry_safe':False,
                    'note':'Preserve entire folder. Do not reset, clear or delete lock to bypass protection.'})
        raise
    finally:
        if link: link.close()

if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: print('Interrupted; preserve output and review before retry.',file=sys.stderr);sys.exit(130)
    except Exception as exc: print('STOP:',exc,file=sys.stderr);sys.exit(1)
