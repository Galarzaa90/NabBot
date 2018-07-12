# Groups
Groups are roles that users can join and leave whenever they want by using the *[group command](../commands/roles.md#group)*.

Only users with the `Manage Roles` command can create and delete groups, while anyone can join/leave them.
Users can create a group from a role higher than their highest role.

The bot requires `Manage Roles` permissions in order to assign or unassign roles.

## Creating groups
Groups can be created using *[group add](../commands/roles.md#group-add)*.
The commands expects only one parameter, the group's name.

A group can be created from an existing role by providing the name (or id) of said role, or a new role can be created for the group.

Once a group has been created, the role can be renamed as much as you want without the need to reassign the group.
However, users always have to type the name (or id) of the group to join, so keep that in mind before using any special characters.

## Deleting groups
A group can be deleted using the *[group remove](../commands/roles.md#group-remove)*.
A group can be removed without deleting the role, making users unable to join/leave the role, or the role can be deleted.

## Joining and leaving groups
To join and leave groups, the user has to use the command *[group](../commands/roles.md#group)*, specifying the name of the group.

If the user is not in the group, he will join it. If the user is already in the group, he will get removed from it.

Users can see a list of available groups using [group list](../commands/roles.md#group-list):

![Example group list](../assets/images/commands/group_list.png)

## Suggested uses
Here are some example uses for groups:

- Groups for vocations, letting users specify their main playing vocation
- Groups for languages or nationalities.
- Groups for quests or bosses, to see who is interested or access related channels.
- Groups to access NSFW content, as a second barrier for NSFW channels.