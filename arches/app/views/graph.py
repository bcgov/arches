'''
ARCHES - a program developed to inventory and manage immovable cultural heritage.
Copyright (C) 2013 J. Paul Getty Trust and World Monuments Fund

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
'''

from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.shortcuts import render
from django.db.models import Q
from django.utils.translation import ugettext as _
from django.http import HttpResponseNotFound
from arches.app.utils.betterJSONSerializer import JSONSerializer, JSONDeserializer
from arches.app.utils.JSONResponse import JSONResponse
from arches.app.models.resource_graphs import ResourceGraph
from arches.app.models import models

@csrf_exempt
def manager(request, nodeid):
    graph = ResourceGraph(nodeid)
    branches = JSONSerializer().serializeToPython(models.BranchMetadata.objects.all())
    branch_nodes = models.Node.objects.filter(~Q(branchmetadata=None), istopnode=True)
    for branch in branches:
        rootnode = branch_nodes.get(branchmetadata_id=branch['branchmetadataid'])
        branch['rootnode'] = rootnode
        branch['graph'] = ResourceGraph(rootnode)

    datatypes = models.DDataType.objects.all()
    return render(request, 'graph-manager.htm', {
        'main_script': 'graph-manager',
        'graph': JSONSerializer().serialize(graph),
        'branches': JSONSerializer().serialize(branches),
        'datatypes': JSONSerializer().serialize(datatypes),
        'node_list': {
            'title': _('Node List'),
            'search_placeholder': _('Find a node in the graph')
        },
        'permissions_list': {
            'title': _('Permissions'),
            'search_placeholder': _('Find a group or user account')
        },
        'branch_list': {
            'title': _('Branch Library'),
            'search_placeholder': _('Find a graph branch')
        }
    })


@csrf_exempt
def node(request, nodeid):
    if request.method == 'POST':
        data = JSONDeserializer().deserialize(request.body)
        if data:
            node = models.Node.objects.get(nodeid=nodeid)
            node_group = node.get_downstream_nodes_and_collectors()
            with transaction.atomic():
                node.name = data.get('name', '')
                node.description = data.get('description','')
                node.istopnode = data.get('istopnode','')
                node.crmclass = data.get('crmclass','')
                node.datatype = data.get('datatype','')
                node.status = data.get('status','')
                new_nodegroup_id = data.get('nodegroup_id','')
                if node.nodegroup_id != new_nodegroup_id:
                    edge = models.Edge.objects.get(rangenode_id=nodeid)
                    parent_group = edge.domainnode.nodegroup
                    new_group = parent_group
                    if new_nodegroup_id == nodeid:
                         new_group, created = models.NodeGroup.objects.get_or_create(nodegroupid=nodeid, defaults={'cardinality': 'n', 'legacygroupid': None, 'parentnodegroup': None})
                         new_group.parentnodegroup = parent_group
                         new_group.save()
                         for collector in node_group['collectors']:
                             collector.nodegroup.parentnodegroup = new_group
                             collector.nodegroup.save()

                    for group_node in node_group['nodes']:
                        group_node.nodegroup = new_group
                        group_node.save()

                    node.nodegroup = new_group

                node.save()
                return JSONResponse({'node': node, 'group_nodes': node_group['nodes'], 'collectors': node_group['collectors']})

    if request.method == 'DELETE':
        data = JSONDeserializer().deserialize(request.body)

        if data:
            with transaction.atomic():
                node = models.Node.objects.get(nodeid=nodeid)
                edge = models.Edge.objects.get(rangenode=node)
                edge.delete()
                graph = ResourceGraph(nodeid)
                for edge in graph.edges:
                    edge.delete()
                for node in graph.nodes:
                    node.delete()
                return JSONResponse({})

    return HttpResponseNotFound()


@csrf_exempt
def append_branch(request, nodeid, property, branchmetadataid):
    if request.method == 'POST':
        graph = ResourceGraph(nodeid)
        newBranch = graph.append_branch(branchmetadataid=branchmetadataid)
        return JSONResponse(newBranch)


    return HttpResponseNotFound()
