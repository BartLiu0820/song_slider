<?php
require '/var/www/html/vendor/autoload.php';
$app=require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
$tokens=Laravel\Sanctum\PersonalAccessToken::where('name','Song deployment integration')->where('tokenable_id',0)->get();
if ($tokens->count() !== 1) { throw new RuntimeException('Expected exactly one workbench integration token'); }
$token=$tokens->first();
$token->abilities=array_values(array_unique(array_merge($token->abilities,['read:sensitive'])));
$token->save();
echo 'Workbench build-log reading enabled; token value unchanged.';
