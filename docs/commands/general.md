!!! note
    The information contained here refers to the `master` branch, it will be updated to `rewrite` documentation soon.

Command parameters are shown in italics, optional parameters are surrounded with `[ ]`

## /choose *option1 option2 ... optionN*

The bot randomly chooses one of the options given. Options with spaces in them must be quoted or they will be considered as multiple options.

Example:  
**/choose "Option A" optionb "Option C"**  
![image](https://cloud.githubusercontent.com/assets/12865379/25460931/01d3cde0-2a9b-11e7-9ddf-c0b094ad5f4a.png)

----


## /uptime

Shows the time the bot has been running.

Example:  
**/uptime**  
![image](https://cloud.githubusercontent.com/assets/12865379/25461342/53762074-2a9d-11e7-9f89-9e089ebfbca2.png)

----

## /about

Shows various information about the bot.

Example:  
**/about**  
![image](https://cloud.githubusercontent.com/assets/12865379/25461399/9b2b0498-2a9d-11e7-8f83-a49ead1f4b02.png)

----

## /events

Shows a list of upcoming and recent events

Example:  
**/event**  
![image](https://cloud.githubusercontent.com/assets/12865379/25461462/12e7dee8-2a9e-11e7-9481-4491776451c2.png)

### Subcommand /events info *id*

Shows details about an event with a specific id. The id can be seen when using /events or after creating an event.

Example:  
**/event info 54**  
![image](https://cloud.githubusercontent.com/assets/12865379/25461524/56615eec-2a9e-11e7-9a96-d6fcbcbb0151.png)

### Subcommand: /events add *starttime* *name*,[description]

Creates an event. The start time must be set by specifying in how much time the event will start from now, e.g. 1d3h20m, 20h4m, 1d20m, 70m. A description for an event is optional.

Once the event is created, the id of the event will be returned. This id is used to edit the event. Events can only be edited by the creator or by bot admins.

Users can only have 2 active events simultaneously.

Example:  
**/event add 3d Inquisition Quest**  
![image](https://cloud.githubusercontent.com/assets/12865379/25461639/f9b74070-2a9e-11e7-989c-425006ac0886.png)

### Subcommand: /event editname *id* *newName*

Edits an event's name.

### Subcommand: /event edittime *id* *newTime*

Edits an event's start time. The same format rules apply

### Subcommand: /event editdescription *id* *newDescription*

Edits an event's description.

### Subcommand: /event delete *id*

Deletes or cancels an event.

### Subcommand: /event subscribe *id*

Lets you subscribe to an upcoming event. Meaning you will receive private messages when the event time is close.

### Subcommand: /event make

Guides you step by step through the event making process.

----

## /server
*Other aliases: /serverinfo*

Shows you various information about the current server. This can't be used on private messages.

Example:  
**/server**  
![image](https://cloud.githubusercontent.com/assets/12865379/25461875/57605472-2aa0-11e7-8533-04be03c42e30.png)

----

## /roles [*userName*]

If no username is specified, a list of all roles in the server is shown. If a user is specified, a list of the roles belonging to the user is shown.

Example:  
**/roles Dozzle**  
![image](https://cloud.githubusercontent.com/assets/12865379/25461939/b437e8f4-2aa0-11e7-9ccb-0c692e5a1c3d.png)

----

## /role *roleName*

Shows a list of members that have the specified role.

Example:  
**/role The Dozzle Cult ☠️**  
![image](https://cloud.githubusercontent.com/assets/12865379/25462021/1a2816ca-2aa1-11e7-99b2-4e80f0bc9b12.png)

