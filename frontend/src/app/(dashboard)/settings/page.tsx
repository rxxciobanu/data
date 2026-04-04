"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useProfile, usePreferences } from "@/hooks/use-user";
import { useApiKeys } from "@/hooks/use-api-keys";
import { useWhaleConfig } from "@/hooks/use-whales";
import { api } from "@/lib/api-client";
import {
  preferencesSchema,
  apiKeySchema,
  type PreferencesForm,
  type ApiKeyForm,
} from "@/lib/validators";
import { formatPercent, formatDate } from "@/lib/utils";
import { Plus, Trash2, Copy, Check } from "lucide-react";
import type { UserPreferences, WhaleConfig, WalletEntry } from "@/types/api";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Settings</h1>
      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="alerts">Alerts</TabsTrigger>
          <TabsTrigger value="sizing">Sizing</TabsTrigger>
          <TabsTrigger value="whales">Whales</TabsTrigger>
          <TabsTrigger value="apikeys">API Keys</TabsTrigger>
        </TabsList>

        <TabsContent value="profile"><ProfileTab /></TabsContent>
        <TabsContent value="alerts"><AlertsTab /></TabsContent>
        <TabsContent value="sizing"><SizingTab /></TabsContent>
        <TabsContent value="whales"><WhalesTab /></TabsContent>
        <TabsContent value="apikeys"><ApiKeysTab /></TabsContent>
      </Tabs>
    </div>
  );
}

function ProfileTab() {
  const { data: profile } = useProfile();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>Your account information</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label>Email</Label>
          <p className="text-sm font-medium">{profile?.email ?? "—"}</p>
        </div>
        <div>
          <Label>User ID</Label>
          <p className="text-sm font-mono text-muted-foreground">
            {profile?.id ?? "—"}
          </p>
        </div>
        <div>
          <Label>Member Since</Label>
          <p className="text-sm text-muted-foreground">
            {profile?.created_at ? formatDate(profile.created_at) : "—"}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function AlertsTab() {
  const { data: prefs, mutate } = usePreferences();
  const [saving, setSaving] = useState(false);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);

  const currentThreshold = threshold ?? prefs?.alert_threshold ?? 0.10;
  const currentEnabled = enabled ?? prefs?.alert_enabled ?? true;

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put<UserPreferences>("/users/me/preferences", {
        alert_threshold: currentThreshold,
        alert_enabled: currentEnabled,
      });
      mutate();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Alert Preferences</CardTitle>
        <CardDescription>
          Configure when you receive trading alerts
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Label>Alerts Enabled</Label>
            <p className="text-sm text-muted-foreground">
              Receive alerts when AI diverges from market
            </p>
          </div>
          <Switch
            checked={currentEnabled}
            onCheckedChange={(v) => setEnabled(v)}
          />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Divergence Threshold</Label>
            <span className="text-sm font-mono">
              {formatPercent(currentThreshold)}
            </span>
          </div>
          <Slider
            value={[currentThreshold * 100]}
            onValueChange={(v) => setThreshold(v[0] / 100)}
            min={1}
            max={50}
            step={1}
          />
          <p className="text-xs text-muted-foreground">
            Only alert when AI vs market divergence exceeds this threshold
          </p>
        </div>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save Preferences"}
        </Button>
      </CardContent>
    </Card>
  );
}

function SizingTab() {
  const { data: prefs, mutate } = usePreferences();
  const [saving, setSaving] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<PreferencesForm>({
    resolver: zodResolver(preferencesSchema),
    values: prefs
      ? {
          alert_threshold: prefs.alert_threshold,
          alert_enabled: prefs.alert_enabled,
          bankroll: prefs.bankroll,
          kelly_fraction: prefs.kelly_fraction,
          max_bet_pct: prefs.max_bet_pct,
          max_total_exposure: prefs.max_total_exposure,
          min_bet_size: prefs.min_bet_size,
        }
      : undefined,
  });

  const onSubmit = async (data: PreferencesForm) => {
    setSaving(true);
    try {
      await api.put<UserPreferences>("/users/me/preferences", data);
      mutate();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Position Sizing</CardTitle>
        <CardDescription>
          Configure Kelly Criterion bet sizing parameters
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)}>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="bankroll">Bankroll ($)</Label>
              <Input
                id="bankroll"
                type="number"
                step="1"
                {...register("bankroll", { valueAsNumber: true })}
              />
              {errors.bankroll && (
                <p className="text-sm text-destructive">
                  {errors.bankroll.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="kelly_fraction">Kelly Fraction</Label>
              <Input
                id="kelly_fraction"
                type="number"
                step="0.01"
                {...register("kelly_fraction", { valueAsNumber: true })}
              />
              {errors.kelly_fraction && (
                <p className="text-sm text-destructive">
                  {errors.kelly_fraction.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="max_bet_pct">Max Bet %</Label>
              <Input
                id="max_bet_pct"
                type="number"
                step="0.01"
                {...register("max_bet_pct", { valueAsNumber: true })}
              />
              {errors.max_bet_pct && (
                <p className="text-sm text-destructive">
                  {errors.max_bet_pct.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="max_total_exposure">Max Total Exposure</Label>
              <Input
                id="max_total_exposure"
                type="number"
                step="0.01"
                {...register("max_total_exposure", { valueAsNumber: true })}
              />
              {errors.max_total_exposure && (
                <p className="text-sm text-destructive">
                  {errors.max_total_exposure.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="min_bet_size">Min Bet Size ($)</Label>
              <Input
                id="min_bet_size"
                type="number"
                step="1"
                {...register("min_bet_size", { valueAsNumber: true })}
              />
              {errors.min_bet_size && (
                <p className="text-sm text-destructive">
                  {errors.min_bet_size.message}
                </p>
              )}
            </div>
          </div>
          <Button type="submit" disabled={saving}>
            {saving ? "Saving..." : "Save Sizing"}
          </Button>
        </CardContent>
      </form>
    </Card>
  );
}

function WhalesTab() {
  const { data: config, mutate } = useWhaleConfig();
  const [saving, setSaving] = useState(false);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [minSize, setMinSize] = useState<string>("");
  const [wallets, setWallets] = useState<WalletEntry[]>([]);
  const [walletsInit, setWalletsInit] = useState(false);
  const [newAddr, setNewAddr] = useState("");
  const [newLabel, setNewLabel] = useState("");

  if (config && !walletsInit) {
    setWallets(config.whale_extra_wallets);
    setWalletsInit(true);
  }

  const currentEnabled = enabled ?? config?.whale_enabled ?? false;
  const currentMinSize =
    minSize !== ""
      ? parseFloat(minSize)
      : (config?.whale_min_trade_size ?? 1000);

  const addWallet = () => {
    if (!newAddr.trim()) return;
    setWallets([...wallets, { address: newAddr.trim(), label: newLabel.trim() }]);
    setNewAddr("");
    setNewLabel("");
  };

  const removeWallet = (index: number) => {
    setWallets(wallets.filter((_, i) => i !== index));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put<WhaleConfig>("/whales/config", {
        whale_enabled: currentEnabled,
        whale_min_trade_size: currentMinSize,
        whale_extra_wallets: wallets,
      });
      mutate();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Whale Tracking</CardTitle>
        <CardDescription>
          Track large traders and get signals on their activity
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Label>Whale Tracking Enabled</Label>
            <p className="text-sm text-muted-foreground">
              Include whale signals in your alerts
            </p>
          </div>
          <Switch
            checked={currentEnabled}
            onCheckedChange={(v) => setEnabled(v)}
          />
        </div>
        <div className="space-y-2">
          <Label>Min Trade Size ($)</Label>
          <Input
            type="number"
            value={minSize || currentMinSize}
            onChange={(e) => setMinSize(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label>Tracked Wallets</Label>
          {wallets.map((w, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-sm font-mono flex-1">{w.address}</span>
              <Badge variant="outline">{w.label || "No label"}</Badge>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => removeWallet(i)}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <div className="flex gap-2">
            <Input
              placeholder="Wallet address"
              value={newAddr}
              onChange={(e) => setNewAddr(e.target.value)}
            />
            <Input
              placeholder="Label"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              className="w-32"
            />
            <Button variant="outline" size="icon" onClick={addWallet}>
              <Plus className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save Whale Config"}
        </Button>
      </CardContent>
    </Card>
  );
}

function ApiKeysTab() {
  const { data: keys, createKey, deleteKey } = useApiKeys();
  const [showCreate, setShowCreate] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [copied, setCopied] = useState(false);
  const [creating, setCreating] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ApiKeyForm>({
    resolver: zodResolver(apiKeySchema),
  });

  const onSubmit = async (data: ApiKeyForm) => {
    setCreating(true);
    try {
      const result = await createKey(data.label);
      setNewKey(result.raw_key);
      reset();
    } finally {
      setCreating(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(newKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>API Keys</CardTitle>
            <CardDescription>
              Manage API keys for programmatic access
            </CardDescription>
          </div>
          <Dialog open={showCreate} onOpenChange={setShowCreate}>
            <DialogTrigger>
              <Button size="sm">
                <Plus className="h-4 w-4 mr-2" />
                Create Key
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create API Key</DialogTitle>
                <DialogDescription>
                  Create a new API key for programmatic access.
                </DialogDescription>
              </DialogHeader>
              {newKey ? (
                <div className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Copy this key now. You won&apos;t see it again.
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 rounded bg-muted p-2 text-xs break-all">
                      {newKey}
                    </code>
                    <Button variant="outline" size="icon" onClick={handleCopy}>
                      {copied ? (
                        <Check className="h-4 w-4" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                  <Button
                    className="w-full"
                    onClick={() => {
                      setNewKey("");
                      setShowCreate(false);
                    }}
                  >
                    Done
                  </Button>
                </div>
              ) : (
                <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="label">Label</Label>
                    <Input
                      id="label"
                      placeholder="e.g. My Bot"
                      {...register("label")}
                    />
                    {errors.label && (
                      <p className="text-sm text-destructive">
                        {errors.label.message}
                      </p>
                    )}
                  </div>
                  <Button type="submit" className="w-full" disabled={creating}>
                    {creating ? "Creating..." : "Create Key"}
                  </Button>
                </form>
              )}
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {!keys || keys.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No API keys yet. Create one for programmatic access.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Prefix</TableHead>
                <TableHead>Label</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Last Used</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((key) => (
                <TableRow key={key.id}>
                  <TableCell className="font-mono">{key.key_prefix}...</TableCell>
                  <TableCell>{key.label || "—"}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(key.created_at)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {key.last_used ? formatDate(key.last_used) : "Never"}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => deleteKey(key.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
