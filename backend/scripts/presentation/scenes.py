from config import BASE


async def perform(a, scene, state):
    p=a.p; kind=scene['kind']
    if kind in ('dashboard','intro','outro'):
        await a.go('/dashboard');a.mark('start');await a.wait(2)
        await a.optional('workspace-all-tools');await a.wait(2)
        await p.keyboard.press('Escape');await a.wheel(230);await a.wait(2)
    elif kind=='assistant':
        await a.go('/assistant','assistant-input');a.mark('start')
        modes=p.locator('select:has(option[value="fast"])')
        if await modes.count(): await modes.first.select_option('fast')
        await a.type(p.get_by_test_id('assistant-input'),'Avant de repeindre un appartement, quelles sont les trois vérifications prioritaires ? Réponds brièvement en français.')
        await a.click(p.get_by_test_id('assistant-send-btn'));a.mark('sent')
        await p.get_by_test_id('assistant-send-btn').wait_for(timeout=150000)
        a.mark('response');await a.wait(2);await a.wheel(150)
    elif kind=='documents':
        await a.go('/assistant?conversation='+state['quote_conversation'],'assistant-input');a.mark('start')
        response=p.locator('[data-message-role="assistant"]').first
        await response.wait_for(timeout=30000)
        panel=p.locator('.assistant-messages')
        await panel.evaluate('(el)=>el.scrollTo({top:0,behavior:"smooth"})');await a.wait(2.5)
        await a.optional('assistant-attach-toggle');await a.wait(1.5)
        await a.optional('assistant-attach-toggle');await a.wait(1)
        await response.scroll_into_view_if_needed();await a.wait(2)
        last=response.locator('li, p').last
        if await last.count():await last.scroll_into_view_if_needed()
        await a.wait(3)
    elif kind=='quote':
        await a.go('/assistant?conversation='+state['quote_conversation'],'assistant-input');a.mark('start')
        link=p.locator('[data-testid^="assistant-quote-tracking-"]').last
        await link.wait_for(timeout=30000);await link.scroll_into_view_if_needed();await a.wait(3)
        await a.cue('quote','Un clic sur Suivi devis')
        await a.click(link)
        await p.get_by_test_id('quote-row-'+state['quote_id']).wait_for(timeout=30000);await a.wait(2)
        await p.get_by_test_id('quote-row-'+state['quote_id']).scroll_into_view_if_needed();await a.wait(3)
    elif kind=='editor':
        await a.go('/devis-editeur/'+state['quote_id'],'editor-line-price-0');a.mark('start')
        await a.wait(2);await p.get_by_test_id('editor-line-designation-0').scroll_into_view_if_needed();await a.wait(2)
        # Focus real editable values, but never click send/PDF/signature controls.
        await a.click(p.get_by_test_id('editor-line-qty-0'));await a.wait(2)
        await p.locator('[data-testid="editor-line-total-2"]').scroll_into_view_if_needed();await a.wait(2)
        await a.wheel(360)
    elif kind in ('radar','prospection'):
        await a.go('/radar','radar-page');a.mark('start');await a.wait(2)
        await a.wheel(220)
        cards=p.locator('[data-testid^="radar-opp-"]')
        await cards.first.wait_for(timeout=30000)
        if kind=='radar':
            await a.cue('radar','ouvrons une fiche')
            await a.click(cards.first);await a.wait(3);await a.wheel(180)
        else:
            await a.click(cards.first);await a.wait(2)
            message=p.get_by_test_id('radar-letter-message');await message.scroll_into_view_if_needed()
            await a.click(message);await a.wait(3)
            await p.get_by_test_id('radar-ai-tone').select_option('chaleureux');await a.wait(2)
    elif kind in ('measure','analysis'):
        await a.go('/plan?open='+state['plan_id'],'plan-canvas');a.mark('start')
        if kind=='measure':
            await a.cue('measure',"J'active la mesure")
            await a.click(p.get_by_test_id('tool-distance'))
            await a.optional('tool-fullscreen');await a.wait(1)
            canvas=p.get_by_test_id('plan-canvas');await canvas.scroll_into_view_if_needed()
            box=await canvas.bounding_box()
            for x,y in [(.26,.48),(.69,.48)]:
                await p.mouse.move(box['x']+box['width']*x,box['y']+box['height']*y,steps=32);await a.wait(.7)
                await p.mouse.click(box['x']+box['width']*x,box['y']+box['height']*y);await a.wait(1.3)
            await p.mouse.move(28,28,steps=25)
            await a.wait(2)
        else:
            await a.click(p.get_by_test_id('tab-ai'));await a.wait(2);await a.wheel(260)
            await a.wait(2);await a.click(p.get_by_test_id('tab-rooms'));await a.wait(2)
    elif kind=='autocad':
        await a.go('/plan?open='+state['autocad_plan_id'],'plan-canvas');a.mark('start')
        toggle=p.get_by_test_id('cad-import-info-toggle')
        await toggle.wait_for(timeout=15000);await a.click(toggle)
        await p.get_by_test_id('cad-import-info-provider').wait_for();await a.wait(5)
        await a.wheel(160);await a.wait(2)
    elif kind=='management':
        await a.go('/devis','saved-quotes-title');a.mark('start')
        await a.tour(['/factures','/situations','/bibliotheque','/rentabilite'])
    elif kind=='team':
        await a.go('/suivi-chantier');a.mark('start');await a.wait(2)
        await a.tour(['/equipe','/rh'])
    elif kind=='tools':
        await a.go('/estimation');a.mark('start');await a.wait(2)
        await a.tour(['/smart-project','/calculateurs','/photo','/etudes-pc','/appro','/rendu-ia'])
    else: raise ValueError(kind)