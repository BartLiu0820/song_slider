<?php
require '/var/www/html/vendor/autoload.php';
$app = require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();

$settings = App\Models\InstanceSettings::findOrFail(0);
$settings->fill([
    'instance_name' => 'Song Deploy',
    'instance_timezone' => 'Asia/Shanghai',
    'fqdn' => null, // Workbench owns deploy.greatsong.online; engine stays on SSH
    'is_registration_enabled' => false,
    'is_api_enabled' => true,
    'is_auto_update_enabled' => false,
    'is_sponsorship_popup_enabled' => false,
    'do_not_track' => true,
    'docker_registry_url' => 'ghcr.io',
]);
$settings->save();
$server = App\Models\Server::findOrFail(0);
$server->name = 'Song Ubuntu';
$server->save();
$server->settings->concurrent_builds = 1;
$server->settings->wildcard_domain = 'https://preview.greatsong.online';
$server->settings->is_sentinel_enabled = false;
$server->settings->save();
$team = App\Models\Team::findOrFail(0);
$team->show_boarding = false;
$team->save();
$user = App\Models\User::findOrFail(0);
$user->current_team_id = 0;
$user->save();
session(['currentTeam' => $team]);
$result = ['configured' => true, 'server_uuid' => $server->uuid,
    'registration_enabled' => $settings->is_registration_enabled];
if (getenv('ISSUE_TOKEN') === '1') {
    $result['token'] = $user->createToken('Song deployment integration',
        ['read', 'read:sensitive', 'write', 'deploy'], now()->addDays(90))->plainTextToken;
}
echo json_encode($result);
