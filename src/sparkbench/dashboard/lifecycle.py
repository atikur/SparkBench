"""Read-only linkage of accepted project, proposal, artifacts and bench records."""
def firmware_status(project, planner, execution):
    accepted=project.get('accepted');links=project.get('firmware_links',[])
    current=[l for l in links if accepted and l['accepted_sha256']==accepted['sha256']]
    jobs=execution.list();proposal=None;build=None
    if current:
        try:proposal=planner.get(current[-1]['proposal_id'])
        except (ValueError,KeyError,OSError):pass
    related=[j for j in jobs if proposal and j.get('proposal_id')==proposal['id'] and j.get('plan_sha256')==proposal.get('plan_sha256')]
    build=next((j for j in related if j['action']=='compile' and j['status']=='compiled'),None)
    installation=next((j for j in related if j['action']=='install' and j['status']=='installed' and build and j.get('firmware_sha256')==build.get('firmware_sha256')),None)
    test=next((j for j in related if j['action']=='test' and j.get('request',{}).get('build_id')==(build or {}).get('id')),None)
    try:
        board,_=execution._board();active=board['active_firmware']
        recorded={k:active.get(k) for k in ['proposal_id','plan_sha256','firmware_sha256','date','runtime_identity','installation_record']}
    except (ValueError,KeyError,OSError):recorded=None
    matches=bool(build and installation and recorded and recorded['firmware_sha256']==build.get('firmware_sha256') and recorded['plan_sha256']==proposal.get('plan_sha256'))
    identity=(recorded or {}).get('runtime_identity') if matches else None
    if not accepted:state='accept_brief'
    elif not current:state='prepare_proposal'
    elif not proposal:state='proposal_unavailable'
    elif proposal['status'] in ('queued','generating'):state='planning'
    elif proposal['status']!='ready':state=proposal['status']
    elif proposal.get('review_status')!='reviewed':state='review'
    elif not build:state='compile'
    elif not matches:state='install'
    elif not identity or identity.get('status')!='pass':state='check_identity'
    else:state='installed'
    active_job=next((j for j in related if j['status']=='running'),None)
    latest_install=next((j for j in jobs if j['action']=='install'),None)
    uncertain=False
    if latest_install and latest_install['status'] in ('incomplete','interrupted'):
        try:
            info=execution.diagnostics(latest_install['id'])['installation']
            uncertain=bool(info and info['status']!='installed_hash_verified' and info['write_attempted'] and info.get('recovery')!='previous_application_restored_hash_verified')
        except (ValueError,OSError):uncertain=True
    if uncertain:state='firmware_unconfirmed'
    return {'state':state,'accepted_sha256':accepted['sha256'] if accepted else None,
            'proposal':{k:proposal.get(k) for k in ['id','status','review_status','plan_sha256']} if proposal else None,
            'build':{k:build.get(k) for k in ['id','firmware_sha256','firmware_bytes']} if build else None,
            'installation_job_id':installation['id'] if installation else None,'recorded_installed':recorded,
            'matches_recorded_installation':matches and not uncertain,'runtime_identity':identity,
            'active_job':{k:active_job.get(k) for k in ['id','action','stage']} if active_job else None,
            'camera_result':{k:test.get(k) for k in ['id','status','physical_verification','shutdown']} if test else None,
            'recent_jobs':[{k:j.get(k) for k in ['id','action','status','stage','error','started_at_utc']} for j in related[:8]],
            'scope':'Recorded installation and UART checks. Opening this status does not contact the board, camera or Meta.'}
