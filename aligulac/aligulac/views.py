import os
from datetime import datetime

from django.contrib.auth import logout
from django.shortcuts import render_to_response, redirect
from django.template.loader import render_to_string
from django.http import HttpResponse, HttpResponseNotFound
from django.core.context_processors import csrf
from django.db.models import Sum, Q
from django.contrib.auth.models import User

from ratings.models import Rating, Period, Player, Team, Match
from ratings.tools import find_player

from blog.models import Post

import simplejson

from countries import transformations

def base_ctx(section=None, subpage=None, request=None, context=None):
    curp = Period.objects.filter(computed=True).order_by('-start')[0]
    menu = [('Ranking', '/periods/%i' % curp.id),\
            ('Teams', '/teams/'),\
            ('Records', '/records/'),\
            ('Results', '/results/'),\
            ('Predict', '/predict/'),\
            ('About', '/faq/'),\
            ('Admin', '/add/')]

    base = {'curp': curp, 'menu': menu}

    if section == 'Records':
        base['submenu'] = [('HoF', '/records/?race=hof'),\
                           ('All', '/records/?race=all'),\
                           ('Protoss', '/records/?race=P'),\
                           ('Terran', '/records/?race=T'),\
                           ('Zerg', '/records/?race=Z')]
    elif section == 'Results':
        base['submenu'] = [('By Date', '/results/'),\
                           ('By Event', '/results/events/'),\
                           ('Search', '/results/search/')]
    elif section == 'Admin':
        base['submenu'] = [('Misc', '/add/misc/'),\
                           ('Matches', '/add/'),\
                           ('Events', '/add/events/')]
    elif section == 'Ranking':
        base['submenu'] = [('Current', '/periods/%i' % curp.id),\
                           ('History', '/periods/')]
    elif section == 'About':
        base['submenu'] = [('FAQ', '/faq/'),
                           ('Blog', '/blog/'),
                           ('Database', '/db/')]

    if section != None:
        base['curpage'] = section

    if subpage != None:
        base['cursubpage'] = subpage

    if request != None:
        base['adm'] = request.user.is_authenticated()

    if context != None:
        if type(context) == Player:
            rating = Rating.objects.filter(player=context, comp_rat__isnull=False).order_by('-period')

            base['submenu'] += [None, ('%s:' % context.tag, '/players/%i' % context.id)]

            if rating.exists():
                base['submenu'].append(('Rating history', '/players/%i/historical/' % context.id))

            base['submenu'].append(('Match history', '/players/%i/results/' % context.id))

            if rating.exists():
                base['submenu'].append(('Adjustments', '/players/%i/period/%i' % (context.id, rating[0].period.id)))

    return base

def db(request):
    base = base_ctx('About', 'Database', request)

    ngames = Match.objects.all().aggregate(Sum('sca'))['sca__sum'] + Match.objects.all().aggregate(Sum('scb'))['scb__sum']
    nmatches = Match.objects.all().count()
    npartial = Match.objects.exclude(eventobj__isnull=True, event='').count()
    nfull = Match.objects.filter(eventobj__isnull=False).count()
    nuntreated = Match.objects.filter(treated=False, period__computed=True).count()
    nplayers = Player.objects.all().count()
    nkoreans = Player.objects.filter(country='KR').count()
    nteams = Team.objects.all().count()
    nactive = Team.objects.filter(active=True).count()
    ninactive = Team.objects.filter(active=False).count()

    base.update({'ngames': ngames, 'nmatches': nmatches, 'npartial': npartial, 'nfull': nfull, 'nuntreated': nuntreated,\
            'nplayers': nplayers, 'nkoreans': nkoreans, 'nteams': nteams,\
            'nactive': nactive, 'ninactive': ninactive})

    submitters = []
    for u in User.objects.exclude(username='admin'):
        n = Match.objects.filter(submitter=u).count()
        if n > 0:
            submitters.append((u, n))
    submitters.sort(key=lambda t: t[1], reverse=True)
    base['submitters'] = submitters[:3]

    dumpfile = '/usr/local/www/media/al/aligulac.sql'
    base['dump'] = os.path.exists(dumpfile)
    if base['dump']:
        stat = os.stat(dumpfile)
        base['megabytes'] = float(stat.st_size)/1048576
        base['modified'] = datetime.fromtimestamp(stat.st_mtime)

    return render_to_response('db.html', base)

def home(request):
    base = base_ctx()

    period = Period.objects.filter(computed=True).order_by('-start')[0]
    entries = Rating.objects.filter(period=period, decay__lt=4, dev__lte=0.2).order_by('-rating')[0:10]

    blogs = Post.objects.order_by('-date')[0:3]

    base.update({'entries': entries, 'blogposts': blogs})
    
    return render_to_response('index.html', base)

def search(request, q=''):
    base = base_ctx()

    if q == '':
        q = request.GET['q']

    players = find_player(q.split(' '), make=False, soft=True)
    teams = Team.objects.filter(Q(name__icontains=q) | Q(alias__name__icontains=q)).distinct()

    if players.count() == 1 and teams.count() == 0:
        return redirect('/players/' + str(players[0].id))
    elif players.count() == 0 and teams.count() == 1:
        return redirect('/teams/' + str(teams[0].id))

    base.update({'players': players, 'query': q, 'teams': teams})

    return render_to_response('search.html', base)

def api_search(request, q=''):
    if q == '':
        q = request.GET['q']

    players = Player.objects.filter(tag__icontains=q)
    d = []
    for p in players:
        dp = {'tag': p.tag, 'race': p.race}
        if p.country != None and p.country != '':
            dp['country'] = transformations.cc_to_cn(p.country)

        try:
            r = Rating.objects.filter(player=p).order_by('-period__id')[0]
            dp['rating'] = r.rating
            dp['rating_vp'] = r.rating_vp
            dp['rating_vt'] = r.rating_vt
            dp['rating_vz'] = r.rating_vz
            dp['dev'] = r.dev
            dp['dev_vp'] = r.dev_vp
            dp['dev_vt'] = r.dev_vt
            dp['dev_vz'] = r.dev_vz
        except:
            dp['rating'] = 0
            dp['rating_vp'] = 0
            dp['rating_vt'] = 0
            dp['rating_vz'] = 0
            dp['dev'] = 0.6
            dp['dev_vp'] = 0.6
            dp['dev_vt'] = 0.6
            dp['dev_vz'] = 0.6

        d.append(dp)

    return HttpResponse(simplejson.dumps(d), mimetype='application/json')

def logoutv(request):
    logout(request)

    return redirect('/add/')

def changepwd(request):
    base = base_ctx()

    if not request.user.is_authenticated():
        base.update(csrf(request))
        return render_to_response('login.html', base)

    base.update({'user': request.user.username})

    if not ('old' in request.POST and 'new' in request.POST and 'newre' in request.POST):
        base.update(csrf(request))
        return render_to_response('changepwd.html', base)

    if not request.user.check_password(request.POST['old']):
        base.update({'wrong_old': True})
        base.update(csrf(request))
        return render_to_response('changepwd.html', base)
    
    if request.POST['new'] != request.POST['newre']:
        base.update({'no_match': True})
        base.update(csrf(request))
        return render_to_response('changepwd.html', base)

    request.user.set_password(request.POST['new'])
    request.user.save()

    return redirect('/add/')

def h404(request):
    base = base_ctx()

    return HttpResponseNotFound(render_to_string('404.html', base))
